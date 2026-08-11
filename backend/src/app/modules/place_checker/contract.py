from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.explorer.public import (
    ExplorerBudget,
    ExplorerPeople,
    ExplorerPlace,
    RequestedItem,
    SourceNote,
)
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


CoverageStatus = Literal["sufficient", "insufficient"]


class PlaceCheckerInput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    input_adm: str = Field(alias="input_ADM", min_length=1, max_length=120)
    places: list[ExplorerPlace] | None = None
    input_items: list[RequestedItem] | None = None
    url_notes: list[SourceNote] | None = None
    days: int = Field(default=3, ge=1, le=30)
    budget: ExplorerBudget = Field(default_factory=ExplorerBudget)
    people: ExplorerPeople = Field(default_factory=ExplorerPeople)
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)

    def trip_intent(self) -> TripIntent:
        return TripIntent(
            destination=self.input_adm,
            days=self.days,
            budget=float(self.budget.target_amount) if self.budget.target_amount else None,
            people=self.people.total,
            preferences=self.short_preferences,
            avoids=self.short_avoids,
        )

    def candidates(self) -> list[PlaceCandidate]:
        values = []
        for place in self.places or []:
            source = place.source_places[0]
            values.append(PlaceCandidate(
                name=place.name,
                source=source.origin,
                source_url=source.source_url,
                confidence=place.confidence,
            ))
        return values


class PlaceCheckerOutput(BaseModel):
    places: list[VerifiedPlace] = Field(default_factory=list)
    rejected_candidates: list[PlaceCandidate] = Field(default_factory=list)
    coverage_status: CoverageStatus
    warnings: list[str] = Field(default_factory=list)
