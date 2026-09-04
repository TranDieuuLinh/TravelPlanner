from app.modules.supervisor.contract import SupervisorDecision, SupervisorInput


def build_fallback_decision(
    payload: SupervisorInput,
    *,
    warning: str,
) -> SupervisorDecision:
    if payload.has_itinerary and payload.has_edit_operation:
        return _decision("plan_editor", warning, "Structured edit state is complete.")
    return SupervisorDecision(
        route="finish",
        confidence=0.0,
        reason="Supervisor LLM was unavailable; no semantic fallback was attempted.",
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
