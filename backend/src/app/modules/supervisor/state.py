from typing import TypedDict

from app.modules.supervisor.contract import SupervisorDecision


class SupervisorState(TypedDict, total=False):
    message: str
    has_itinerary: bool
    has_edit_operation: bool
    decision: SupervisorDecision
