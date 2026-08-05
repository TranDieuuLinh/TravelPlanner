from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.domain.entities import DestinationStay
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import (
    AccommodationRequirement,
    BudgetEnvelope,
    PlanningIntent,
    TransportRequirement,
    TripPlanningSpec,
)


class TripTiming(BaseModel):
    days: int = Field(default=3, ge=1, le=30)
    start_date: Annotated[str | None, Field(default=None, alias="startDate")]
    end_date: Annotated[str | None, Field(default=None, alias="endDate")]
    flexibility: Literal["unknown", "fixed", "flexible"] = "unknown"
    destination_stays: Annotated[
        list[DestinationStay],
        Field(default_factory=list, alias="destinationStays"),
    ]

    model_config = {"populate_by_name": True}


class TravelParty(BaseModel):
    type: Literal["solo", "couple", "family", "friends", "group", "other"] = (
        "solo"
    )
    adults: int = Field(default=1, ge=1, le=50)
    children: int = Field(default=0, ge=0, le=50)
    infants: int = Field(default=0, ge=0, le=20)
    pets: int = Field(default=0, ge=0, le=20)
    rooms: int = Field(default=1, ge=1, le=20)

    @property
    def party_size(self) -> int:
        return self.adults + self.children + self.infants

    @model_validator(mode="after")
    def infer_type_when_omitted(self) -> "TravelParty":
        if "type" in self.model_fields_set:
            return self
        if self.children or self.infants:
            self.type = "family"
        elif self.adults == 2:
            self.type = "couple"
        elif self.adults > 2:
            self.type = "group"
        return self


TravelPartyType = Literal["solo", "couple", "family", "friends", "group", "other"]


class TripPreferences(BaseModel):
    travel_style: Annotated[str, Field(default="local", alias="travelStyle")]
    pace: TravelPace = TravelPace.balanced
    interests: list[str] = Field(default_factory=list)
    must_visit_places: Annotated[
        list[str], Field(default_factory=list, alias="mustVisitPlaces")
    ]
    avoid_places: Annotated[
        list[str], Field(default_factory=list, alias="avoidPlaces")
    ]
    accommodation: AccommodationRequirement = Field(
        default_factory=AccommodationRequirement
    )
    transport: TransportRequirement = Field(default_factory=TransportRequirement)

    model_config = {"populate_by_name": True}


class TripConstraints(BaseModel):
    items: list[str] = Field(default_factory=list)
    policy: ConstraintPolicy = Field(default_factory=ConstraintPolicy)


class TripIntent(BaseModel):
    """Canonical, versioned brief for one trip.

    This aggregate is the only persisted representation of trip intent. The
    Planner's older PlanningIntent/TripPlanningSpec objects are projections,
    not persistence contracts.
    """

    destination: str
    timing: TripTiming = Field(default_factory=TripTiming)
    travel_party: Annotated[
        TravelParty,
        Field(default_factory=TravelParty, alias="travelParty"),
    ]
    budget: BudgetEnvelope = Field(default_factory=BudgetEnvelope)
    notes: list[str] = Field(default_factory=list)
    preferences: TripPreferences = Field(default_factory=TripPreferences)
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    clarifying_questions: Annotated[
        list[str], Field(default_factory=list, alias="clarifyingQuestions")
    ]

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_dates(self) -> "TripIntent":
        if bool(self.timing.start_date) != bool(self.timing.end_date):
            raise ValueError("startDate and endDate must be provided together")
        if (
            self.timing.start_date
            and self.timing.end_date
            and "flexibility" not in self.timing.model_fields_set
        ):
            self.timing.flexibility = "fixed"
        self.preferences.accommodation.guest_count = self.travel_party.party_size
        self.preferences.accommodation.room_count = self.travel_party.rooms
        return self

    @classmethod
    def from_planning_context(
        cls,
        intent: PlanningIntent,
        trip_spec: TripPlanningSpec,
        *,
        notes: list[str] | None = None,
    ) -> "TripIntent":
        party_type: TravelPartyType = "solo"
        if trip_spec.party_size == 2:
            party_type = "couple"
        elif trip_spec.party_size > 2:
            party_type = "group"
        return cls(
            destination=intent.destination,
            timing=TripTiming(
                days=trip_spec.days,
                startDate=trip_spec.start_date,
                endDate=trip_spec.end_date,
                flexibility=(
                    "fixed"
                    if trip_spec.start_date and trip_spec.end_date
                    else "unknown"
                ),
                destinationStays=intent.destination_stays,
            ),
            travelParty=TravelParty(
                type=party_type,
                adults=trip_spec.party_size,
                rooms=trip_spec.accommodation.room_count,
            ),
            budget=trip_spec.budget,
            notes=notes or [],
            preferences=TripPreferences(
                travelStyle=intent.travel_style,
                pace=intent.pace,
                interests=intent.interests,
                mustVisitPlaces=intent.must_visit_places,
                avoidPlaces=intent.avoid_places,
                accommodation=trip_spec.accommodation,
                transport=trip_spec.transport,
            ),
            constraints=TripConstraints(
                items=intent.constraints,
                policy=intent.constraint_policy,
            ),
            clarifyingQuestions=intent.clarifying_questions,
        )

    def to_planning_intent(self) -> PlanningIntent:
        return PlanningIntent(
            destination=self.destination,
            travelStyle=self.preferences.travel_style,
            pace=self.preferences.pace,
            interests=self.preferences.interests,
            mustVisitPlaces=self.preferences.must_visit_places,
            avoidPlaces=self.preferences.avoid_places,
            constraints=self.constraints.items,
            destinationStays=self.timing.destination_stays,
            constraintPolicy=self.constraints.policy,
            clarifyingQuestions=self.clarifying_questions,
        )

    def to_trip_spec(self) -> TripPlanningSpec:
        accommodation = self.preferences.accommodation.model_copy(
            update={
                "room_count": self.travel_party.rooms,
                "guest_count": self.travel_party.party_size,
            }
        )
        return TripPlanningSpec(
            days=self.timing.days,
            partySize=self.travel_party.party_size,
            startDate=self.timing.start_date,
            endDate=self.timing.end_date,
            accommodation=accommodation,
            transport=self.preferences.transport,
            budget=self.budget,
        )
