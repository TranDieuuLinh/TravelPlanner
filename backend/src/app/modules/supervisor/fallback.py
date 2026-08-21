import re
import unicodedata

from app.modules.supervisor.contract import SupervisorDecision, SupervisorInput


def build_fallback_decision(
    payload: SupervisorInput,
    *,
    warning: str,
) -> SupervisorDecision:
    message = _normalize(payload.message)
    if payload.has_itinerary and payload.has_edit_operation:
        return _decision("plan_editor", warning, "Structured edit state is complete.")
    if payload.has_source_input or _contains(
        message,
        "lap ke hoach",
        "len ke hoach",
        "len plan",
        "lap lich trinh",
        "len lich trinh",
        "plan a trip",
        "create itinerary",
    ) or _looks_like_trip_request(message):
        return _decision("explorer", warning, "Clear planning intent matched locally.")
    if _contains(
        message,
        "toi muon biet",
        "thong tin",
        "gia ve",
        "gio mo cua",
        "co gi",
        "thi sao",
        "nen di dau",
        "where",
        "what to do",
        "opening hours",
    ):
        return _decision(
            "information_finder",
            warning,
            "Clear travel-information intent matched locally.",
        )
    if _looks_like_destination_prompt(payload.message):
        return _decision(
            "information_finder",
            warning,
            "Short destination prompt routed to travel information.",
        )
    if re.fullmatch(r"(xin )?chao[.! ]*", message):
        return SupervisorDecision(
            route="finish",
            confidence=0.8,
            reason="Greeting matched by deterministic fallback.",
            response="Xin chào! Penguin có thể giúp bạn tìm thông tin du lịch hoặc lập kế hoạch chuyến đi.",
            warnings=[warning],
        )
    return SupervisorDecision(
        route="finish",
        confidence=0.0,
        reason="Không thể xác định yêu cầu bằng Supervisor LLM.",
        response=(
            "Penguin chưa thể hiểu chắc yêu cầu lúc này. Bạn có thể nói rõ "
            "mình cần tìm thông tin, lên kế hoạch hay chỉnh sửa lịch trình không?"
        ),
        clarification_question="Bạn muốn Penguin hỗ trợ việc gì?",
        warnings=[warning],
    )


def _decision(route: str, warning: str, reason: str) -> SupervisorDecision:
    return SupervisorDecision(
        route=route,
        confidence=0.75,
        reason=reason,
        warnings=[warning],
    )


def _normalize(value: str) -> str:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(ascii_value.replace("đ", "d").split())


def _contains(value: str, *phrases: str) -> bool:
    return any(phrase in value for phrase in phrases)


def _looks_like_trip_request(value: str) -> bool:
    """Recognize the short planning prompts commonly used in the chat UI.

    The LLM classifier is optional in development and test environments. A
    prompt such as ``đi Hà Nội 2 ngày`` still contains enough structure to
    route to Explorer without treating general questions containing "đi" as
    trip-planning requests.
    """
    has_trip_verb = re.search(r"\b(di|du lich|nghi duong|tham quan)\b", value)
    has_duration = re.search(r"\b\d+\s*(ngay|dem)\b", value)
    has_planning_intent = re.search(
        r"\b(muon di du lich|muon di|tim noi|chon noi|goi y noi|"
        r"nhieu hoat dong|nhieu trai nghiem|phu hop voi)\b",
        value,
    )
    return bool(has_trip_verb and (has_duration or has_planning_intent))


def _looks_like_destination_prompt(value: str) -> bool:
    """Route a short place-only prompt to Finder during classifier fallback.

    A message such as ``Đà Lạt`` contains no explicit question words, but in a
    travel chat it conventionally asks for an overview. Keep this heuristic
    narrow so greetings, long ambiguous requests and planning prompts do not
    get rerouted.
    """
    raw = " ".join(value.strip().split())
    normalized = _normalize(raw)
    words = normalized.split()
    if not 1 < len(words) <= 4:
        return False
    if _contains(
        normalized,
        "xin chao",
        "toi muon",
        "hay",
        "cho toi",
        "lap",
        "ke hoach",
        "di ",
    ):
        return False
    return not re.search(r"[?!.,;:]", raw)
