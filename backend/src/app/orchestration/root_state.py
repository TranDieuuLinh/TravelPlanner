from typing import TypedDict

from app.modules.conversation_memory.public import (
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.explorer.public import ExplorerImageInput, ExplorerOutput
from app.modules.information_finder.public import InformationFinderOutput
from app.modules.itinerary_planner.public import (
    ItineraryPlannerInput,
    ItineraryPlannerOutput,
    PlannerPreflightFailure,
)
from app.modules.place_checker.public import (
    PlaceCheckerFailure,
    PlaceCheckerOutput,
    PlaceCheckerResult,
)
from app.modules.plan_editor.public import EditOperation
from app.modules.supervisor.public import SupervisorDecision
from app.shared.contracts.itinerary import Itinerary
from app.shared.contracts.trip import TripIntent


class RootState(TypedDict, total=False):
    request_id: str
    message: str
    conversation_context: list[str]
    urls: list[str]
    images: list[ExplorerImageInput]
    force_refresh: bool
    existing_itinerary: Itinerary | None
    edit_operation: EditOperation | None

    conversation_memory: WorkingMemoryState | dict | None
    recent_messages: list[str]
    conversation_summary: str | None
    resolved_references: list[MemoryReference] | list[dict]

    decision: SupervisorDecision
    explorer_output: ExplorerOutput
    information_output: InformationFinderOutput
    place_output: PlaceCheckerOutput | PlaceCheckerResult | PlaceCheckerFailure
    planner_input: ItineraryPlannerInput
    planner_output: ItineraryPlannerOutput
    planner_preflight_failure: PlannerPreflightFailure
    planner_error_code: str
    intent: TripIntent
    itinerary: Itinerary

    response: str
    clarification_question: str | None
    pending_user_context: list[dict]
    suggestions: list[dict[str, object]]
    warnings: list[str]
