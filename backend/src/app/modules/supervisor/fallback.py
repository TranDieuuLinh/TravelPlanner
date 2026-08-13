from app.modules.supervisor.contract import SupervisorDecision


def build_fallback_decision(*, warning: str) -> SupervisorDecision:
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
