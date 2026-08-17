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
    ):
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
