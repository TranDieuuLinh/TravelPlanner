from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.shared.contracts.source_note import SourceNote


class PlannerContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class CandidatePriority(StrEnum):
    user_input = "user_input"
    url = "url"
    special_experience = "special_experience"
    special_near = "special_near"


class CandidateSourceKind(StrEnum):
    special_experience = "special_experience"
    offer_item = "offer_item"
    both = "both"
    generic = "generic"


class CandidateTimeSource(StrEnum):
    place = "place"
    activity_item = "activity_item"
    has_style = "has_style"
    source_hint = "source_hint"
    unknown = "unknown"


class MealType(StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"


class MissingMealSlot(PlannerContractModel):
    day: int = Field(ge=1, le=30)
    meal: MealType


class MealSlotAssignment(MissingMealSlot):
    restaurant_id: str = Field(min_length=1, max_length=300)


class FoodCoverageFeasibility(PlannerContractModel):
    days: int = Field(default=0, ge=0, le=30)
    hard_complete: bool = False
    reserve_complete: bool = False
    hard_assignments: list[MealSlotAssignment] = Field(default_factory=list)
    hard_missing_slots: list[MissingMealSlot] = Field(default_factory=list)
    reserve_assignments: list[MealSlotAssignment] = Field(default_factory=list)
    reserve_missing_slots: list[MissingMealSlot] = Field(default_factory=list)


class PlannerPreflightFailure(PlannerContractModel):
    code: Literal["missing_meal_coverage"] = "missing_meal_coverage"
    missing: list[MissingMealSlot] = Field(min_length=1, max_length=90)


class TimeInterval(PlannerContractModel):
    start_minute: int = Field(ge=0, le=1440)
    end_minute: int = Field(ge=0, le=1440)


class PlannerCoordinates(PlannerContractModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PlannerDailyBudgetEstimate(PlannerContractModel):
    accommodation: int = Field(ge=0)
    food: int = Field(ge=0)
    local_transport: int = Field(ge=0)
    activities: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def total_matches_components(self) -> PlannerDailyBudgetEstimate:
        expected = (
            self.accommodation + self.food + self.local_transport + self.activities
        )
        if self.total != expected:
            raise ValueError("daily budget total must equal its components")
        return self


class PlannerBudget(PlannerContractModel):
    amount: float | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    source: Literal["explicit", "estimated_daily_cost", "unspecified"] = "unspecified"
    daily_estimate: PlannerDailyBudgetEstimate | None = None
    profile_version: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("currency must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def source_fields_are_consistent(self) -> PlannerBudget:
        if self.source == "explicit" and self.amount is None:
            raise ValueError("explicit budget requires amount")
        if self.source == "estimated_daily_cost" and (
            self.amount is None
            or self.daily_estimate is None
            or not self.profile_version
        ):
            raise ValueError(
                "estimated budget requires amount, daily estimate, and version"
            )
        return self


class PlannerPrice(PlannerContractModel):
    cost: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("currency must be a three-letter code")
        return normalized


class PlannerTrip(PlannerContractModel):
    destination: str = Field(min_length=1, max_length=200)
    days: int = Field(ge=1, le=30)
    start_date: date
    timezone: str = Field(min_length=1, max_length=100)
    people: int = Field(ge=1, le=100)
    budget: PlannerBudget
    preferences: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


OpeningHours = dict[str, list[TimeInterval] | None] | None


class PlannerCandidate(PlannerContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=300)
    coordinates: PlannerCoordinates
    address: str | None = Field(default=None, max_length=1000)
    priority: CandidatePriority
    notes: SourceNote | None = None
    tags: list[str] = Field(default_factory=list, max_length=100)
    image_urls: list[str] = Field(default_factory=list, max_length=20)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    duration_minutes: int = Field(gt=0, le=1440)
    opening_hours: OpeningHours = None
    preferred_time_windows: list[TimeInterval] = Field(
        default_factory=list,
        max_length=20,
    )
    source_kind: CandidateSourceKind = CandidateSourceKind.generic
    offered_activity_ids: list[str] = Field(default_factory=list, max_length=100)
    time_source: CandidateTimeSource = CandidateTimeSource.unknown
    price: PlannerPrice
    relationships: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("relationships")
    @classmethod
    def deduplicate_relationships(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))


class PlannerFoodCandidate(PlannerCandidate):
    supported_meals: list[MealType] = Field(min_length=1, max_length=3)

    @field_validator("supported_meals")
    @classmethod
    def deduplicate_meals(cls, values: list[MealType]) -> list[MealType]:
        return list(dict.fromkeys(values))


class PlannerAccommodation(PlannerContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=300)
    coordinates: PlannerCoordinates
    address: str | None = Field(default=None, max_length=1000)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    price_per_night: PlannerPrice


class UpstreamCandidateExclusion(PlannerContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=300)
    priority: CandidatePriority
    reason_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


class ItineraryPlannerInput(PlannerContractModel):
    trip: PlannerTrip
    places: list[PlannerCandidate] = Field(default_factory=list, max_length=500)
    food: list[PlannerFoodCandidate] = Field(default_factory=list, max_length=500)
    food_coverage: FoodCoverageFeasibility = Field(
        default_factory=FoodCoverageFeasibility
    )
    accommodations: list[PlannerAccommodation] = Field(
        default_factory=list,
        max_length=3,
    )
    excluded_candidates: list[UpstreamCandidateExclusion] = Field(
        default_factory=list,
        max_length=500,
    )
    upstream_warnings: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_candidate_identity_and_days(self) -> ItineraryPlannerInput:
        candidates = [*self.places, *self.food]
        ids = [candidate.place_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("placeId must be unique across places and food")

        for candidate in candidates:
            if candidate.opening_hours is None:
                continue
            for raw_day in candidate.opening_hours:
                try:
                    day = int(raw_day)
                except ValueError as exc:
                    raise ValueError(
                        "openingHours keys must be trip day numbers"
                    ) from exc
                if str(day) != raw_day or not 1 <= day <= self.trip.days:
                    raise ValueError(
                        "openingHours keys must be canonical trip day numbers"
                    )
        accommodation_ids = [item.place_id for item in self.accommodations]
        if len(accommodation_ids) != len(set(accommodation_ids)):
            raise ValueError("accommodation placeId must be unique")
        if set(ids) & set(accommodation_ids):
            raise ValueError("accommodation placeId must not overlap stop candidates")
        if self.food_coverage.days not in {0, self.trip.days}:
            raise ValueError("foodCoverage days must match trip days")
        return self
