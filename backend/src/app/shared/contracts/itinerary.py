from pydantic import BaseModel, Field, model_validator

from app.shared.contracts.place import VerifiedPlace
from app.shared.contracts.trip import TripIntent


class ItineraryItem(BaseModel):
    item_id: str
    place: VerifiedPlace
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(gt=0, le=1440)
    travel_minutes_from_previous: int = Field(default=0, ge=0)
    locked: bool = False

    @model_validator(mode="after")
    def ends_after_start(self) -> "ItineraryItem":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be after start_minute")
        return self


class ItineraryDay(BaseModel):
    day: int = Field(ge=1, le=30)
    items: list[ItineraryItem] = Field(default_factory=list)


class Itinerary(BaseModel):
    itinerary_id: str
    intent: TripIntent
    days: list[ItineraryDay]
    total_estimated_cost: float = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
