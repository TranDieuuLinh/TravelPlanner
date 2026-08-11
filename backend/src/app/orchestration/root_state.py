from typing import TypedDict

from app.modules.explorer.public import ExplorerImageInput, ExplorerOutput
from app.modules.information_finder.public import InformationFinderOutput
from app.modules.plan_editor.public import EditOperation
from app.modules.place_checker.public import PlaceCheckerOutput
from app.modules.supervisor.public import SupervisorDecision
from app.shared.contracts.itinerary import Itinerary
from app.shared.contracts.trip import TripIntent


class RootState(TypedDict, total=False):
    request_id: str
    message: str
    urls: list[str]
    images: list[ExplorerImageInput]
    force_refresh: bool
    existing_itinerary: Itinerary | None
    edit_operation: EditOperation | None

    decision: SupervisorDecision
    explorer_output: ExplorerOutput
    information_output: InformationFinderOutput
    place_output: PlaceCheckerOutput
    intent: TripIntent
    itinerary: Itinerary

    response: str
    clarification_question: str | None
    warnings: list[str]
