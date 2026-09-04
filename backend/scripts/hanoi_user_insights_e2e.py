from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from app.core.config import get_settings
from app.modules.explorer.public import create_explorer_service
from app.modules.itinerary_planner.public import (
    build_valhalla_cp_sat_first_itinerary_planner_graph,
)
from app.modules.place_checker.factory import build_postgres_place_checker_pipeline
from app.modules.supervisor.adapters import GeminiIntentClassifier
from app.modules.supervisor.public import SupervisorService
from app.orchestration.root_graph import create_root_graph
from app.shared.llm import GeminiLlmClient


CASES = [
    {
        "id": "01_solo_low_history",
        "profile": "Đi một mình, ngân sách thấp, lịch sử và ẩm thực địa phương",
        "prompt": (
            "Tôi đi Hà Nội một mình trong 2 ngày, ngân sách 1,5 triệu đồng mỗi "
            "người. Tôi thích lịch sử, văn hóa và ẩm thực địa phương; muốn đi "
            "Văn Miếu - Quốc Tử Giám, Hoàng thành Thăng Long, Hồ Hoàn Kiếm, ăn "
            "phở và bún chả. Tránh nightlife, quán bar và nơi quá đông."
        ),
    },
    {
        "id": "02_couple_high_scenic",
        "profile": "Cặp đôi, ngân sách cao, cảnh quan và thư giãn",
        "prompt": (
            "Hai người lớn đi Hà Nội 2 ngày, ngân sách 6 triệu đồng mỗi người. "
            "Ưu tiên cảnh quan, chụp ảnh, ẩm thực và thư giãn; muốn đi Hồ Tây, "
            "Chùa Trấn Quốc, Hồ Hoàn Kiếm và Phố cổ Hà Nội, ăn tối tại nhà hàng "
            "Việt. Tránh nơi quá ồn và hoạt động mạo hiểm."
        ),
    },
    {
        "id": "03_family_children",
        "profile": "Gia đình có trẻ em, ngân sách trung bình, hoạt động phù hợp trẻ",
        "prompt": (
            "Gia đình gồm 2 người lớn và 2 trẻ em đi Hà Nội 2 ngày, ngân sách 2 "
            "triệu đồng mỗi người. Ưu tiên nơi phù hợp trẻ em, thiên nhiên, kiến "
            "thức và ẩm thực; muốn đi Bảo tàng Dân tộc học Việt Nam, Công viên "
            "Thủ Lệ và Hồ Hoàn Kiếm. Tránh nightlife, rượu bia và hoạt động mạo hiểm."
        ),
    },
    {
        "id": "04_senior_spiritual",
        "profile": "Hai người lớn tuổi, lịch sử và tâm linh, nhịp độ nhẹ",
        "prompt": (
            "Hai người lớn tuổi đi Hà Nội 2 ngày, ngân sách 3 triệu đồng mỗi người. "
            "Ưu tiên lịch sử, tâm linh, cảnh quan và lịch trình thư thả; muốn đi "
            "Lăng Chủ tịch Hồ Chí Minh, Chùa Một Cột, Chùa Trấn Quốc và Đền Quán "
            "Thánh. Tránh đi bộ xa, nightlife và hoạt động mạo hiểm."
        ),
    },
]


class TimingCallback(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.starts: dict[UUID, tuple[str, float, str]] = {}
        self.records: list[dict[str, Any]] = []

    async def on_chain_start(
        self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs
    ) -> None:
        self.starts[run_id] = (
            self._name("chain", serialized, kwargs),
            perf_counter(),
            "chain",
        )

    async def on_llm_start(
        self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs
    ) -> None:
        self.starts[run_id] = (
            self._name("llm", serialized, kwargs),
            perf_counter(),
            "llm",
        )

    async def on_chain_end(self, outputs, *, run_id, **kwargs) -> None:
        self._finish(run_id, "success")

    async def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        self._finish(run_id, "success")

    async def on_chain_error(self, error, *, run_id, **kwargs) -> None:
        self._finish(run_id, "error")

    async def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        self._finish(run_id, "error")

    def _finish(self, run_id: UUID, status: str) -> None:
        active = self.starts.pop(run_id, None)
        if active is None:
            return
        name, started, kind = active
        self.records.append(
            {
                "name": name,
                "kind": kind,
                "status": status,
                "durationMs": round((perf_counter() - started) * 1000, 2),
            }
        )

    @staticmethod
    def _name(kind: str, serialized: Any, kwargs: dict[str, Any]) -> str:
        for key in ("name", "run_name"):
            if isinstance(kwargs.get(key), str) and kwargs[key]:
                return kwargs[key]
        if isinstance(serialized, dict):
            if isinstance(serialized.get("name"), str):
                return serialized["name"]
            identifier = serialized.get("id")
            if isinstance(identifier, list) and identifier:
                return str(identifier[-1])
        return kind


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


def _planner_summary(planner: dict[str, Any] | None) -> dict[str, Any]:
    if not planner:
        return {
            "generated": False,
            "dayCount": 0,
            "stopCount": 0,
            "mealCount": 0,
            "allStopsInHanoiBounds": False,
        }
    days = planner.get("days", [])
    stops = [stop for day in days for stop in day.get("stops", [])]
    in_hanoi = all(
        20.8 <= stop["coordinates"]["latitude"] <= 21.3
        and 105.5 <= stop["coordinates"]["longitude"] <= 106.1
        for stop in stops
    )
    return {
        "generated": True,
        "dayCount": len(days),
        "stopCount": len(stops),
        "mealCount": sum(stop.get("kind") == "food" for stop in stops),
        "allStopsInHanoiBounds": bool(stops) and in_hanoi,
        "totalCostPerPerson": planner.get("totalCostPerPerson"),
        "budgetPerPerson": planner.get("budgetPerPerson"),
        "solverStatus": (planner.get("solver") or {}).get("status"),
        "unscheduledCount": len(planner.get("unscheduled", [])),
        "discardedOptionalCount": planner.get("discardedOptionalCount"),
        "stopNames": [stop.get("name") for stop in stops],
    }


def _compact_timings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interesting = {
        "supervisor",
        "explorer",
        "place_checker",
        "itinerary_planner",
        "finish",
        "gemini.generate",
    }
    return [record for record in records if record["name"] in interesting]


async def run(output_path: Path) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the Hanoi E2E evaluation")
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required for the Hanoi E2E evaluation")

    llm = GeminiLlmClient(
        settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
    )
    supervisor = SupervisorService(
        GeminiIntentClassifier(
            llm,
            max_output_tokens=settings.supervisor_llm_max_output_tokens,
        ),
        fallback_enabled=settings.supervisor_llm_fallback_enabled,
        confidence_threshold=settings.supervisor_llm_confidence_threshold,
    )
    explorer = create_explorer_service(
        draft_provider=settings.explorer_draft_provider,
        source_draft_provider=settings.explorer_source_draft_provider,
        llm_client=llm,
        max_output_tokens=settings.explorer_llm_max_output_tokens,
        source_chunk_characters=settings.explorer_source_chunk_characters,
        source_max_output_tokens=settings.explorer_source_max_output_tokens,
        source_max_concurrency=settings.explorer_source_max_concurrency,
        synthesis_max_concurrency=settings.explorer_synthesis_max_concurrency,
        dedupe_provider=settings.explorer_dedupe_provider,
        note_provider=settings.explorer_note_provider,
        database_url=None,
    )
    place_checker = build_postgres_place_checker_pipeline(
        settings.database_url,
        external_place_search=None,
        llm_client=None,
    )
    planner = build_valhalla_cp_sat_first_itinerary_planner_graph(
        settings.valhalla_base_url,
        timeout_seconds=settings.valhalla_timeout_seconds,
        provider_version=settings.valhalla_graph_version,
        log_search_progress=settings.itinerary_log_search_progress,
    )
    graph = create_root_graph(
        checkpointer=False,
        supervisor_service=supervisor,
        explorer_service=explorer,
        place_checker_pipeline=place_checker,
        itinerary_planner_graph=planner,
    )
    results: list[dict[str, Any]] = []
    try:
        for case in CASES:
            callback = TimingCallback()
            started = perf_counter()
            try:
                state = await graph.ainvoke(
                    {
                        "request_id": f"hanoi-insight-e2e:{case['id']}",
                        "message": case["prompt"],
                        "urls": [],
                        "images": [],
                        "force_refresh": False,
                    },
                    config={"callbacks": [callback]},
                )
                planner_output = _dump(state.get("planner_output"))
                explorer_output = _dump(state.get("explorer_output"))
                planner_input = _dump(state.get("planner_input"))
                results.append(
                    {
                        **case,
                        "status": "success" if planner_output else "no_itinerary",
                        "durationMs": round((perf_counter() - started) * 1000, 2),
                        "route": getattr(state.get("decision"), "route", None),
                        "response": state.get("response"),
                        "clarificationQuestion": state.get("clarification_question"),
                        "warnings": state.get("warnings", []),
                        "explorerOutput": explorer_output,
                        "plannerInput": planner_input,
                        "plannerOutput": planner_output,
                        "plannerSummary": _planner_summary(planner_output),
                        "timings": _compact_timings(callback.records),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        **case,
                        "status": "error",
                        "durationMs": round((perf_counter() - started) * 1000, 2),
                        "error": type(exc).__name__,
                        "message": str(exc)[:1000],
                        "timings": _compact_timings(callback.records),
                    }
                )
    finally:
        catalog = place_checker.context_builder.adm_resolver
        close = getattr(catalog, "close", None)
        if close is not None:
            await close()
        await llm.aclose()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            [
                {
                    "id": result["id"],
                    "status": result["status"],
                    "durationMs": result["durationMs"],
                    "route": result.get("route"),
                    "response": result.get("response"),
                    "warnings": result.get("warnings", []),
                    "plannerSummary": result.get("plannerSummary"),
                }
                for result in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
