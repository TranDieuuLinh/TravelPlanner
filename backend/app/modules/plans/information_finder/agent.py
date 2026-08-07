"""Read-only conversation runtime for travel information requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .reader import PlaceSearchReader
from .schema import InformationQuery, InformationResult


@dataclass(frozen=True)
class InformationFinderResponse:
    message: str
    blocks: list[dict[str, Any]]
    result: InformationResult | None = None


class InformationFinderAgent:
    """Run information requests without mutating a plan or revision."""

    def __init__(self, reader: PlaceSearchReader | None = None) -> None:
        self.reader = reader

    async def run(self, context: Any) -> InformationFinderResponse:
        intent = _intent(context)
        if intent == "explain_plan":
            return _explain_plan(context)
        if intent == "travel_advice":
            response_text = _decision_response(context)
            if response_text:
                return InformationFinderResponse(
                    message=response_text,
                    blocks=[{"type": "text", "text": response_text}],
                )
        query = _query(context)
        if query is None:
            return _clarification(context)
        if intent != "ask_place":
            message = "Mình chưa có nguồn dữ liệu đủ mới cho câu hỏi này."
            return InformationFinderResponse(
                message=message,
                blocks=[
                    {"type": "text", "text": message},
                    {"type": "warning", "code": "SOURCE_UNKNOWN_OR_STALE", "message": "Nguồn hoặc độ mới chưa được xác nhận.", "freshness": "unknown/stale"},
                ],
            )
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


def _decision_response(context: Any) -> str | None:
    decision = getattr(context, "decision", None)
    value = getattr(decision, "message", None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


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


def _explain_plan(context: Any) -> InformationFinderResponse:
    plan = getattr(context, "plan", None)
    if plan is None:
        text = "Chat này chưa có plan để giải thích."
        return InformationFinderResponse(text, [{"type": "text", "text": text}])
    lines = [f"Plan {plan.title} tại {plan.destination} gồm {len(plan.days)} ngày."]
    refs: list[str] = []
    for day in plan.days:
        lines.append(f"Ngày {day.day}: {day.theme} ({len(day.items)} điểm).")
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
