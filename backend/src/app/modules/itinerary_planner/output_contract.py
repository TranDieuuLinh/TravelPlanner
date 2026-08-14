from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    MealType,
    PlannerContractModel,
    PlannerCoordinates,
)


class ItineraryStop(PlannerContractModel):
    place_id: str
    name: str
    kind: Literal["place", "food"]
    priority: CandidatePriority
    start_minute: int = Field(ge=0, le=1620)
    end_minute: int = Field(gt=0, le=1620)
    duration_minutes: int = Field(gt=0, le=1440)
    meal_type: MealType | None = None
    coordinates: PlannerCoordinates
    address: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    cost_per_person: int = Field(ge=0)


class ItineraryRouteLeg(PlannerContractModel):
    from_place_id: str
    to_place_id: str
    duration_minutes: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    encoded_polyline: str | None = None
    provider: str
    geometry_available: bool


class ItineraryDay(PlannerContractModel):
    day: int = Field(ge=1, le=30)
    date: date
    stops: list[ItineraryStop]
    legs: list[ItineraryRouteLeg]
    activity_minutes: int = Field(ge=0)
    travel_minutes: int = Field(ge=0)
    cost_per_person: int = Field(ge=0)


class UnscheduledPriority(PlannerContractModel):
    place_id: str
    name: str
    priority: CandidatePriority
    reason_code: str
    message: str


class SolverPassMetadata(PlannerContractModel):
    name: str
    status: str
    objective_value: int
    wall_time_ms: int = Field(ge=0)
    optimality_proven: bool


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
    days: list[ItineraryDay]
    total_cost_per_person: int = Field(ge=0)
    budget_per_person: float | None = Field(default=None, ge=0)
    currency: str
    solver: SolverMetadata
    source_mix: list[SourceMixAudit] = Field(default_factory=list)
    unscheduled: list[UnscheduledPriority]
    discarded_optional_count: int = Field(ge=0)
    warnings: list[str]
    phase_timings_ms: dict[str, int]
