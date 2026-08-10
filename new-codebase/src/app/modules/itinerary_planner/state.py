from typing import TypedDict

from app.modules.itinerary_planner.contract import ItineraryPlannerOutput
from app.shared.contracts.place import VerifiedPlace
from app.shared.contracts.trip import TripIntent


class ItineraryPlannerState(TypedDict, total=False):
    intent: TripIntent
    places: list[VerifiedPlace]
    upstream_warnings: list[str]
    output: ItineraryPlannerOutput

