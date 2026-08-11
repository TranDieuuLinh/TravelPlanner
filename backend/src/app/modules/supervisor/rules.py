import re
import unicodedata

from app.modules.supervisor.contract import SupervisorDecision, SupervisorInput


def normalize_message(message: str) -> str:
    decomposed = unicodedata.normalize("NFD", message.casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_marks).strip()


def structured_edit_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    if payload.has_itinerary and payload.has_edit_operation:
        return SupervisorDecision(
            route="plan_editor",
            confidence=1.0,
            reason="Structured edit and itinerary are present.",
        )
    return None


def edit_clarification_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    if not _contains_edit_request(message):
        return None
    if payload.has_itinerary and payload.has_edit_operation:
        return None
    return SupervisorDecision(
        route="finish",
        confidence=0.98,
        reason="An edit request lacks required structured state.",
        response="I need an existing itinerary and a structured edit operation to update a plan.",
        clarification_question=(
            "Please provide the itinerary and structured edit operation before editing."
        ),
        warnings=["Plan edit was not executed."],
    )


def planning_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    has_planning_phrase = _contains_any(
        message,
        (
            "lap ke hoach",
            "len ke hoach",
            "tao lich trinh",
            "goi y dia diem",
            "goi y lich trinh",
            "ke hoach du lich",
            "chuyen di",
            "hanh trinh",
            "plan a trip",
            "trip plan",
            "create an itinerary",
            "plan my trip",
            "suggest places",
            "what should i do",
            "where should i go",
            "nen di dau",
            "travel itinerary",
            "travel plan",
        ),
    )
    has_trip_context = _contains_any(
        message,
        ("trip", "travel", "itinerary", "du lich", "lich trinh", "chuyen"),
    )
    if not has_planning_phrase and not (
        _has_duration_signal(message) and has_trip_context
    ):
        return None
    return SupervisorDecision(
        route="explorer",
        confidence=0.94,
        reason="The message contains a clear trip-planning signal.",
    )


def information_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    if not _contains_any(
        message,
        (
            "thong tin",
            "thoi tiet",
            "gio mo cua",
            "gia ve",
            "phi vao cua",
            "dia chi",
            "quy dinh",
            "mo cua luc",
            "weather",
            "opening hours",
            "business hours",
            "ticket price",
            "admission fee",
            "address",
            "regulations",
            "entry requirements",
            "visa requirement",
            "compare ",
            "how much does",
            "what time does",
            "is it open",
            "tell me about",
            "current information",
            "latest information",
        ),
    ):
        return None
    return SupervisorDecision(
        route="information_finder",
        confidence=0.93,
        reason="The message contains a clear travel-information signal.",
    )


def greeting_or_scope_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    if _is_greeting_or_thanks(message):
        return SupervisorDecision(
            route="finish",
            confidence=0.99,
            reason="The message is a greeting or thanks.",
            response="Hello! I can help plan trips and find travel information.",
        )
    if _contains_any(
        message,
        (
            "write a poem",
            "write code",
            "debug this",
            "solve this math",
            "recipe for",
            "stock price",
            "political campaign",
        ),
    ):
        return SupervisorDecision(
            route="finish",
            confidence=0.97,
            reason="The request is outside travel-planning scope.",
            response="I can help with travel planning and destination information.",
        )
    return None


def deterministic_decision(payload: SupervisorInput) -> SupervisorDecision | None:
    for rule in (
        structured_edit_rule,
        edit_clarification_rule,
        planning_rule,
        information_rule,
        greeting_or_scope_rule,
    ):
        decision = rule(payload)
        if decision is not None:
            return decision
    return None


def fallback_decision(
    payload: SupervisorInput, *, warning: str | None = None
) -> SupervisorDecision:
    warnings = [warning] if warning else []
    return SupervisorDecision(
        route="explorer",
        confidence=0.35,
        reason="Intent is ambiguous; trip-planning clarification is safest.",
        warnings=warnings,
    )


def _contains_edit_request(message: str) -> bool:
    return _contains_any(
        message,
        (
            "xoa",
            "them",
            " doi ",
            " sua ",
            "di chuyen",
            "remove",
            "edit",
            "delete",
            "move",
            "add",
            "update",
            "cap nhat",
        ),
    )


def _has_duration_signal(message: str) -> bool:
    return bool(re.search(r"\b\d{1,2}\s*(ngay|day|days|dem|night|nights)\b", message))


def _is_greeting_or_thanks(message: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:xin chao|chao|hello|hi|hey|good morning|good afternoon|cam on|thank you|thanks)(?:[ ,.].*)?",
            message,
        )
    )


def _contains_any(message: str, markers: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(marker.strip())}(?!\w)", message) is not None
        for marker in markers
    )
