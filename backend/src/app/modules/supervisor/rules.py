import re
import unicodedata

from app.modules.supervisor.contract import SupervisorDecision, SupervisorInput


def normalize_message(message: str) -> str:
    decomposed = unicodedata.normalize("NFD", message.casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_marks.replace("đ", "d")).strip()


def structured_edit_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    if payload.has_itinerary and payload.has_edit_operation:
        return SupervisorDecision(
            route="plan_editor",
            confidence=1.0,
            reason="Da co lich trinh va thao tac chinh sua co cau truc.",
        )
    return None


def source_import_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    if payload.has_source_input:
        return SupervisorDecision(
            route="explorer",
            confidence=1.0,
            reason="URL hoac hinh anh can duoc Explorer phan tich.",
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
        reason="Yeu cau chinh sua chua co du trang thai co cau truc.",
        response="Tôi cần lịch trình hiện có và thao tác chỉnh sửa có cấu trúc để cập nhật kế hoạch.",
        clarification_question=(
            "Vui long cung cap lich trinh va thao tac chinh sua co cau truc truoc khi chinh sua."
        ),
        warnings=["Chua thuc hien chinh sua ke hoach."],
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
            "plan a three-day trip",
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
        reason="Tin nhan co tin hieu ro rang ve viec lap ke hoach chuyen di.",
    )


def information_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    has_information_signal = _contains_any(
        message,
        (
            "thong tin",
            "lich su",
            "lich sua",
            "van hoa",
            "am thuc",
            "dan so",
            "ngon ngu",
            "y nghia",
            "dac diem",
            "muon biet them",
            "gioi thieu ve",
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
            "what about",
        ),
    )
    if not has_information_signal and not _is_destination_follow_up(message):
        return None
    if _is_destination_follow_up(message):
        return SupervisorDecision(
            route="information_finder",
            confidence=0.91,
            reason="Day la cau hoi noi tiep ve thong tin diem den.",
        )
    return SupervisorDecision(
        route="information_finder",
        confidence=0.93,
        reason="Tin nhan co tin hieu ro rang ve cau hoi kien thuc du lich.",
    )


def greeting_or_scope_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    message = normalize_message(payload.message)
    if _is_greeting_or_thanks(message):
        return SupervisorDecision(
            route="finish",
            confidence=0.99,
            reason="The message is a greeting or thanks.",
            response=(
                "Penguin xin chào! Bạn muốn Penguin giúp tìm thông tin về một "
                "địa điểm, lên kế hoạch chuyến đi hay chỉnh sửa lịch trình?"
            ),
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
            response=(
                "Penguin có thể giúp bạn lên kế hoạch chuyến đi, tìm thông tin "
                "địa điểm và chỉnh sửa lịch trình."
            ),
        )
    return None


def contextual_follow_up_rule(payload: SupervisorInput) -> SupervisorDecision | None:
    if not payload.conversation_context:
        return None
    message = normalize_message(payload.message)
    if not re.fullmatch(r"(?:con|the con)\s+.+", message):
        return None
    return SupervisorDecision(
        route="information_finder",
        confidence=0.9,
        reason="Ngu canh hoi thoai cho thay day la cau hoi noi tiep ve thong tin du lich.",
    )


def deterministic_decision(payload: SupervisorInput) -> SupervisorDecision | None:
    for rule in (
        structured_edit_rule,
        source_import_rule,
        contextual_follow_up_rule,
        planning_rule,
        information_rule,
        edit_clarification_rule,
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
        route="finish",
        confidence=0.35,
        reason="Y dinh chua ro; Supervisor can nguoi dung lam ro yeu cau.",
        response=(
            "Penguin chưa chắc đã hiểu đúng yêu cầu. Bạn muốn lập kế hoạch, "
            "tìm thông tin du lịch hay chỉnh sửa lịch trình?"
        ),
        clarification_question=(
            "Bạn có thể nói rõ mục tiêu hoặc nội dung cần tôi xử lý không?"
        ),
        warnings=warnings,
    )


def _contains_edit_request(message: str) -> bool:
    return _contains_any(
        message,
        (
            "xoa",
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
    ) or re.search(
        r"\bthem\s+(?:diem|muc|hoat dong|ngay|mon|place|item|activity)", message
    ) is not None


def _has_duration_signal(message: str) -> bool:
    return bool(re.search(r"\b\d{1,2}\s*(ngay|day|days|dem|night|nights)\b", message))


def _is_greeting_or_thanks(message: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:xin chao|chao|hello|hi|hey|good morning|good afternoon|cam on|thank you|thanks|ban khoe khong|dao nay ban the nao|ban la ai|ban co the lam gi)(?:[ ,.?!].*)?",
            message,
        )
    )


def _is_destination_follow_up(message: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:con|the con)\s+.+?\s+thi sao[?.! ]*",
            message,
        )
        or re.fullmatch(r"what about\s+.+?[?.! ]*", message)
    )


def _contains_any(message: str, markers: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(marker.strip())}(?!\w)", message) is not None
        for marker in markers
    )
