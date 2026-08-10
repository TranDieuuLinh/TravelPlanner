from pydantic import BaseModel, Field

from app.shared.contracts.itinerary import Itinerary
from app.shared.contracts.place import VerifiedPlace
from app.shared.contracts.trip import TripIntent


class ItineraryPlannerInput(BaseModel):
    intent: TripIntent
    places: list[VerifiedPlace] = Field(default_factory=list)
    upstream_warnings: list[str] = Field(default_factory=list)


class ItineraryPlannerOutput(BaseModel):
    itinerary: Itinerary

