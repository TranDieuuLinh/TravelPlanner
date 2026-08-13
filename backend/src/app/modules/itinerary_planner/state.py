from typing import TypedDict

from app.modules.itinerary_planner.contract import (
    ItineraryPlannerInput,
    ItineraryPlannerOutput,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.shared.contracts.place import VerifiedPlace
from app.shared.contracts.trip import TripIntent


class ItineraryPlannerState(TypedDict, total=False):
    # Phase 2 boundary. Runtime switches to these fields at the integration checkpoint.
    input: ItineraryPlannerInput
    prepared_problem: PreparedPlanningProblem
    warnings: list[str]
    error: str

    # Temporary scaffold fields retained until the root graph integration checkpoint.
    intent: TripIntent
    places: list[VerifiedPlace]
    upstream_warnings: list[str]
    output: ItineraryPlannerOutput
