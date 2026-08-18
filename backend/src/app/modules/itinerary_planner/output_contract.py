from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    MealType,
    OpeningHours,
    PlannerAccommodation,
    PlannerContractModel,
    PlannerCoordinates,
    PlannerDailyBudgetEstimate,
)
from app.shared.contracts.source_note import SourceNote
from app.modules.itinerary_planner.beam_search.evaluation import BeamSearchEvaluation


class ItineraryStop(PlannerContractModel):
    item_id: str
    place_id: str
    name: str
    kind: Literal["place", "food", "entertainment"]
    priority: CandidatePriority
    start_minute: int = Field(ge=0, le=1620)
    end_minute: int = Field(gt=0, le=1620)
    duration_minutes: int = Field(gt=0, le=1440)
    meal_type: MealType | None = None
    coordinates: PlannerCoordinates
    address: str | None = None
    notes: SourceNote | None = None
    personal_notes: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    bayesian_rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    opening_hours: OpeningHours = None
    cost_per_person: int = Field(ge=0)


class ItineraryRouteLeg(PlannerContractModel):
    from_place_id: str
    to_place_id: str
    duration_minutes: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    encoded_polyline: str | None = None
    provider: str
    geometry_available: bool
    cost_per_person: int = Field(default=0, ge=0)


class DailyCostBreakdown(PlannerContractModel):
    accommodation: int = Field(ge=0)
    food: int = Field(ge=0)
    local_transport: int = Field(ge=0)
    activities: int = Field(ge=0)
    misc: int = Field(ge=0)
    total: int = Field(ge=0)
    currency: str

    @model_validator(mode="after")
    def total_matches_components(self) -> DailyCostBreakdown:
        expected = (
            self.accommodation
            + self.food
            + self.local_transport
            + self.activities
            + self.misc
        )
        if self.total != expected:
            raise ValueError("cost breakdown total must equal its components")
        return self


class ItineraryDay(PlannerContractModel):
    day: int = Field(ge=1, le=30)
    date: date
    stops: list[ItineraryStop]
    legs: list[ItineraryRouteLeg]
    activity_minutes: int = Field(ge=0)
    travel_minutes: int = Field(ge=0)
    cost_per_person: int = Field(ge=0)
    cost_breakdown: DailyCostBreakdown

    @model_validator(mode="after")
    def cost_matches_breakdown(self) -> ItineraryDay:
        if self.cost_per_person != self.cost_breakdown.total:
            raise ValueError("cost_per_person must equal cost_breakdown.total")
        return self


class UnscheduledPriority(PlannerContractModel):
    place_id: str
    name: str
    priority: CandidatePriority
    reason_code: str
    message: str
    notes: SourceNote | None = None
    source_refs: list[str] = Field(default_factory=list, max_length=20)


class SolverPassMetadata(PlannerContractModel):
    name: str
    status: str
    objective_value: int
    wall_time_ms: int = Field(ge=0)
    optimality_proven: bool
    attempt_count: int = Field(default=1, ge=1)
    round_count: int = Field(default=1, ge=1)
    no_improvement_rounds: int = Field(default=0, ge=0)


class SolverMetadata(PlannerContractModel):
    status: str
    optimality_proven: bool
    objective_value: int
    objective_policy_version: str
    objective_components: dict[str, int]
    passes: list[SolverPassMetadata]
    planning_time_ms: int = Field(ge=0)


class SourceMixCounts(PlannerContractModel):
    special: int = Field(ge=0)
    offer: int = Field(ge=0)


class SourceMixAudit(PlannerContractModel):
    period: Literal["morning", "evening"]
    target: SourceMixCounts
    actual: SourceMixCounts
    quota_fallback: bool
    fallback_reason: str | None = None


class ItineraryPlannerOutput(PlannerContractModel):
    destination: str
    timezone: str
    people: int = Field(ge=1, le=100)
    accommodation: PlannerAccommodation | None = None
    accommodation_nights: int = Field(default=0, ge=0, le=29)
    days: list[ItineraryDay]
    total_cost_per_person: int = Field(ge=0)
    budget_per_person: float | None = Field(default=None, ge=0)
    budget_source: Literal["explicit", "estimated_daily_cost", "unspecified"] = (
        "unspecified"
    )
    daily_budget_estimate: PlannerDailyBudgetEstimate | None = None
    budget_profile_version: str | None = None
    currency: str
    solver: SolverMetadata
    evaluation: BeamSearchEvaluation | None = None
    source_mix: list[SourceMixAudit] = Field(default_factory=list)
    unscheduled: list[UnscheduledPriority]
    discarded_optional_count: int = Field(ge=0)
    warnings: list[str]
    phase_timings_ms: dict[str, int]
