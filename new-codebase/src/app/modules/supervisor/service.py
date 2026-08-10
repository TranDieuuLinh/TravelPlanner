from app.modules.supervisor.contract import SupervisorDecision, SupervisorInput


class SupervisorService:
    """Deterministic routing baseline that can later be replaced by an LLM port."""

    _INFORMATION_MARKERS = (
        "thông tin",
        "ở đâu",
        "là gì",
        "thời tiết",
        "giờ mở cửa",
        "how",
        "what",
        "where",
    )
    _EDIT_MARKERS = ("xóa", "thêm", "đổi", "sửa", "di chuyển", "remove", "add", "edit")

    def decide(self, payload: SupervisorInput) -> SupervisorDecision:
        normalized = payload.message.casefold()
        if payload.has_itinerary and (
            payload.has_edit_operation
            or any(marker in normalized for marker in self._EDIT_MARKERS)
        ):
            return SupervisorDecision(
                route="plan_editor",
                confidence=0.95,
                reason="An itinerary edit was requested.",
            )
        if any(marker in normalized for marker in self._INFORMATION_MARKERS):
            return SupervisorDecision(
                route="information_finder",
                confidence=0.8,
                reason="The message is an information request.",
            )
        return SupervisorDecision(
            route="explorer",
            confidence=0.75,
            reason="The message is treated as a trip-planning request.",
        )

