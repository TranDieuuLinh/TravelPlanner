"""Read-only conversation runtime for travel information requests."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient

from .reader import PlaceSearchReader
from .schema import InformationAnswer, InformationQuery, InformationResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InformationFinderResponse:
    message: str
    blocks: list[dict[str, Any]]
    result: InformationResult | None = None


class InformationFinderAgent:
    """Run information requests without mutating a plan or revision."""

    def __init__(
        self,
        reader: PlaceSearchReader | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.reader = reader
        self.llm = llm

    async def run(self, context: Any) -> InformationFinderResponse:
        intent = _intent(context)
        if intent == "explain_plan":
            return await self._explain_plan(context)
        if intent == "travel_advice":
            return await self._answer(context, grounded=False)
        if intent == "ask_travel_information":
            return await self._answer(context, grounded=True)
        query = _query(context)
        if query is None:
            return _clarification(context)
        if self.reader is None:
            message = "Hiện chưa có bộ đọc địa điểm để tìm thông tin."
            return InformationFinderResponse(
                message=message,
                blocks=[{"type": "text", "text": message}, {"type": "warning", "code": "READER_UNAVAILABLE", "message": "Place search reader unavailable."}],
            )
        try:
            result = await self.reader.search(query.query, query.destination, query.top_k)
        except Exception:
            message = "Mình chưa thể đọc dữ liệu địa điểm lúc này."
            return InformationFinderResponse(
                message=message,
                blocks=[{"type": "text", "text": message}, {"type": "warning", "code": "PLACE_SEARCH_FAILED", "message": "Place search provider failed."}],
            )
        return _result_response(result)

    async def _answer(
        self,
        context: Any,
        *,
        grounded: bool,
        plan_payload: dict[str, Any] | None = None,
    ) -> InformationFinderResponse:
        query = _query_text(context)
        if not query:
            return _clarification(context)
        if self.llm is None:
            return _llm_unavailable(grounded=grounded)

        payload: dict[str, Any] = {"query": query}
        if plan_payload is not None:
            payload["currentPlan"] = plan_payload
        schema = InformationAnswer.model_json_schema(by_alias=True)
        system_prompt = _answer_system_prompt(
            grounded=grounded,
            explaining_plan=plan_payload is not None,
        )
        try:
            if grounded:
                try:
                    generated = await self.llm.generate_grounded_structured_json(
                        system_prompt,
                        json.dumps(payload, ensure_ascii=False),
                        response_schema=schema,
                    )
                    answer = InformationAnswer.model_validate_json(generated.text)
                    blocks: list[dict[str, Any]] = [
                        {"type": "text", "text": answer.answer}
                    ]
                    if generated.sources:
                        blocks.append(
                            {
                                "type": "sources",
                                "sources": [
                                    {"title": source.title, "url": source.uri}
                                    for source in generated.sources
                                ],
                            }
                        )
                    else:
                        answer = answer.model_copy(
                            update={
                                "answer": (
                                    f"{answer.answer}\n\n"
                                    f"{_freshness_notice(query)}"
                                )
                            }
                        )
                        blocks[0]["text"] = answer.answer
                        blocks.append(
                            {
                                "type": "warning",
                                "code": "GROUNDING_SOURCES_UNAVAILABLE",
                                "message": "Không có nguồn grounding để đối chiếu.",
                                "freshness": "unknown/stale",
                            }
                        )
                    return InformationFinderResponse(answer.answer, blocks)
                except (
                    RuntimeError,
                    ValidationError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    # Grounded search can have a separate quota or capability
                    # failure from normal structured generation. Keep the chat
                    # useful, but label the fallback as unverified/currentness
                    # unknown instead of presenting it as grounded.
                    logger.warning(
                        "Grounded information answer failed; using an ungrounded fallback",
                        extra={"error_type": type(exc).__name__},
                    )
                    raw = await self.llm.generate_structured_json(
                        _answer_system_prompt(
                            grounded=False,
                            explaining_plan=plan_payload is not None,
                        ),
                        json.dumps(payload, ensure_ascii=False),
                        response_schema=schema,
                    )
                    answer = InformationAnswer.model_validate_json(raw)
                    answer = answer.model_copy(
                        update={
                            "answer": f"{answer.answer}\n\n{_freshness_notice(query)}"
                        }
                    )
                    return InformationFinderResponse(
                        answer.answer,
                        [
                            {"type": "text", "text": answer.answer},
                            {
                                "type": "warning",
                                "code": "GROUNDING_UNAVAILABLE",
                                "message": (
                                    "Không thể kiểm tra nguồn mới lúc này; "
                                    "hãy xác minh thông tin có thể thay đổi."
                                ),
                                "freshness": "unknown/stale",
                            },
                        ],
                    )

            raw = await self.llm.generate_structured_json(
                system_prompt,
                json.dumps(payload, ensure_ascii=False),
                response_schema=schema,
            )
            answer = InformationAnswer.model_validate_json(raw)
            blocks = [{"type": "text", "text": answer.answer}]
            if plan_payload is not None:
                refs = _plan_source_refs(context)
                if refs:
                    blocks.append({"type": "sourceRefs", "sourceRefs": refs})
            return InformationFinderResponse(answer.answer, blocks)
        except (RuntimeError, ValidationError, ValueError, json.JSONDecodeError):
            return _answer_failed(grounded=grounded)

    async def _explain_plan(self, context: Any) -> InformationFinderResponse:
        plan = getattr(context, "plan", None)
        if plan is None:
            text = "Chat này chưa có plan để giải thích."
            return InformationFinderResponse(text, [{"type": "text", "text": text}])
        response = await self._answer(
            context,
            grounded=False,
            plan_payload=_plan_summary(plan),
        )
        if any(
            block.get("code") in {"ANSWER_GENERATION_FAILED", "LLM_UNAVAILABLE"}
            for block in response.blocks
        ):
            return _deterministic_plan_summary(context)
        return response


def _intent(context: Any) -> str:
    data = getattr(context, "data", {}) or {}
    decision = getattr(context, "decision", None)
    return str(
        data.get("information_intent")
        or data.get("informationIntent")
        or getattr(decision, "information_intent", None)
        or getattr(decision, "intent", None)
        or "ask_place"
    )


def _destination(context: Any) -> str | None:
    chat = getattr(context, "chat", None)
    plan = getattr(context, "plan", None)
    return getattr(chat, "destination", None) or getattr(plan, "destination", None)


def _query(context: Any) -> InformationQuery | None:
    data = getattr(context, "data", {}) or {}
    raw = getattr(context, "information_query", None) or data.get("information_query") or data.get("informationQuery") or data.get("query")
    if raw is None:
        content = str(getattr(getattr(context, "turn", None), "content", "")).strip()
        raw = {"query": content, "destination": _destination(context)} if content else None
    elif isinstance(raw, str):
        raw = {"query": raw, "destination": _destination(context)}
    if raw is None:
        return None
    try:
        query = raw if isinstance(raw, InformationQuery) else InformationQuery.model_validate(raw)
    except Exception:
        return None
    if _ambiguous(query.query):
        return None
    if query.destination is None:
        query = query.model_copy(update={"destination": _destination(context)})
    return query


def _query_text(context: Any) -> str:
    data = getattr(context, "data", {}) or {}
    value = data.get("query")
    if not isinstance(value, str) or not value.strip():
        value = getattr(getattr(context, "turn", None), "content", "")
    return str(value).strip()


def _ambiguous(query: str) -> bool:
    return " ".join(query.casefold().split()) in {"địa điểm này", "chỗ này", "nơi này", "ở đâu", "thông tin"}


def _clarification(context: Any) -> InformationFinderResponse:
    text = "Bạn muốn tìm địa điểm nào hoặc hỏi thông tin gì?"
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    options = list(getattr(getattr(context, "decision", None), "options", ()) or ())
    if options:
        blocks.append({"type": "optionSelector", "options": options})
    return InformationFinderResponse(text, blocks)


def _result_response(result: InformationResult) -> InformationFinderResponse:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": result.message}]
    if result.candidates:
        blocks.append({"type": "candidateList", "candidates": [item.model_dump(mode="json", by_alias=True) for item in result.candidates], "needsUserChoice": result.needs_user_choice})
        if result.needs_user_choice:
            blocks.append({"type": "optionSelector", "options": [{"label": "Chọn địa điểm", "value": item.candidate_id} for item in result.candidates]})
    for warning in result.warnings:
        blocks.append({"type": "warning", "code": warning, "message": warning})
    return InformationFinderResponse(result.message, blocks, result)


def _deterministic_plan_summary(context: Any) -> InformationFinderResponse:
    plan = getattr(context, "plan", None)
    if plan is None:
        text = "Chat này chưa có plan để giải thích."
        return InformationFinderResponse(text, [{"type": "text", "text": text}])
    lines = [f"Plan {plan.title} tại {plan.destination} gồm {len(plan.days)} ngày."]
    refs: list[str] = []
    for day in plan.days:
        lines.append(f"Ngày {day.day} ({len(day.items)} điểm).")
        for item in day.items:
            refs.extend(item.source_refs)
    text = "\n".join(lines)
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    unique_refs = list(dict.fromkeys(refs))
    if unique_refs:
        blocks.append({"type": "sourceRefs", "sourceRefs": unique_refs})
    else:
        blocks.append({"type": "warning", "code": "PLAN_SOURCES_UNAVAILABLE", "message": "Plan không có source refs để đối chiếu.", "freshness": "unknown/stale"})
    return InformationFinderResponse(text, blocks)


def _plan_summary(plan: Any) -> dict[str, Any]:
    return {
        "title": plan.title,
        "destination": plan.destination,
        "days": [
            {
                "day": day.day,
                "items": [
                    {
                        "itemId": item.item_id,
                        "name": item.name,
                        "timeWindow": item.time_window,
                        "placeType": item.place_type,
                    }
                    for item in day.items
                ],
            }
            for day in plan.days
        ],
    }


def _plan_source_refs(context: Any) -> list[str]:
    plan = getattr(context, "plan", None)
    if plan is None:
        return []
    return list(
        dict.fromkeys(
            ref
            for day in plan.days
            for item in day.items
            for ref in item.source_refs
        )
    )


def _answer_system_prompt(*, grounded: bool, explaining_plan: bool) -> str:
    if explaining_plan:
        return (
            "Bạn là InformationFinderAgent của TravelPlanner. Trả lời bằng tiếng Việt "
            "chỉ dựa trên currentPlan được cung cấp. Không bịa địa điểm, nguồn hoặc lý do "
            "không có trong snapshot. Chỉ trả JSON khớp schema."
        )
    if grounded:
        return (
            "Bạn là InformationFinderAgent của TravelPlanner. Trả lời câu hỏi du lịch "
            "cần dữ liệu mới bằng cùng ngôn ngữ với câu hỏi của người dùng, dựa trên "
            "Google Search grounding. Nêu rõ "
            "điểm chưa chắc chắn và không bịa nguồn. Chỉ trả JSON khớp schema."
        )
    return (
        "Bạn là InformationFinderAgent của TravelPlanner. Trả lời câu hỏi tư vấn, văn hóa, "
        "fun fact hoặc lưu ý du lịch bằng cùng ngôn ngữ với câu hỏi của người dùng, rõ ràng "
        "và hữu ích. Không trình bày "
        "thông tin thời gian thực như đã được xác minh. Chỉ trả JSON khớp schema."
    )


def _freshness_notice(query: str) -> str:
    vietnamese_characters = (
        r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệ"
        r"íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]"
    )
    vietnamese = bool(
        re.search(vietnamese_characters, query.casefold())
        or re.search(
            r"\b(?:mình|tôi|bạn|làm sao|thế nào|ở đâu|việt nam)\b",
            query.casefold(),
        )
    )
    if vietnamese:
        return "Lưu ý: mình chưa thể kiểm tra nguồn mới; hãy xác minh chi tiết có thể thay đổi."
    return "Note: I could not verify live sources, so please confirm details that may change."


def _llm_unavailable(*, grounded: bool) -> InformationFinderResponse:
    message = "Mình chưa thể tạo câu trả lời lúc này."
    code = "GROUNDED_LLM_UNAVAILABLE" if grounded else "LLM_UNAVAILABLE"
    return InformationFinderResponse(
        message,
        [
            {"type": "text", "text": message},
            {"type": "warning", "code": code, "message": message},
        ],
    )


def _answer_failed(*, grounded: bool) -> InformationFinderResponse:
    message = "Mình chưa thể tổng hợp thông tin lúc này."
    code = "GROUNDED_ANSWER_FAILED" if grounded else "ANSWER_GENERATION_FAILED"
    return InformationFinderResponse(
        message,
        [
            {"type": "text", "text": message},
            {
                "type": "warning",
                "code": code,
                "message": message,
                **({"freshness": "unknown/stale"} if grounded else {}),
            },
        ],
    )
