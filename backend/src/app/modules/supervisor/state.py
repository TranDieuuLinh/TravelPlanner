from typing import TypedDict

from app.modules.supervisor.contract import SupervisorDecision


class SupervisorState(TypedDict, total=False):
    message: str
    conversation_context: list[str]
    has_source_input: bool
    has_itinerary: bool
    has_edit_operation: bool
    destination: str | None
    duration_days: int | None
    mentioned_places: list[str]
    selected_places: list[str]
    clarification_required: bool
    user_context_requests: list[dict]
    pending_user_context: list[dict]
    conversation_summary: str | None
    decision: SupervisorDecision
