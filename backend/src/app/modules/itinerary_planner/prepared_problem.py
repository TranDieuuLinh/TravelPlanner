from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    MealType,
    PlannerAccommodation,
    PlannerCandidate,
    PlannerEntertainmentCandidate,
    PlannerFoodCandidate,
    PlannerTrip,
)
from app.modules.itinerary_planner.time_windows import PlanningWindow

Candidate = PlannerCandidate | PlannerFoodCandidate | PlannerEntertainmentCandidate
CandidateDay = tuple[str, int]
MealSlot = tuple[str, int, MealType]


@dataclass(frozen=True, slots=True)
class CandidateExclusion:
    place_id: str
    name: str
    priority: CandidatePriority
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class MissingMealCoverage:
    day: int
    meal: MealType


class PlanningPreflightError(ValueError):
    def __init__(self, missing_meals: tuple[MissingMealCoverage, ...]) -> None:
        self.missing_meals = missing_meals
        details = ", ".join(
            f"day {item.day} {item.meal.value}" for item in missing_meals
        )
        super().__init__(f"No feasible food candidate for: {details}")


@dataclass(frozen=True, slots=True)
class PreparedPlanningProblem:
    trip: PlannerTrip
    accommodations: tuple[PlannerAccommodation, ...]
    accommodation_by_id: Mapping[str, PlannerAccommodation]
    valid_places: tuple[PlannerCandidate, ...]
    valid_food: tuple[PlannerFoodCandidate, ...]
    valid_entertainment: tuple[PlannerEntertainmentCandidate, ...]
    candidate_by_id: Mapping[str, Candidate]
    feasible_days: Mapping[str, frozenset[int]]
    preferred_days: Mapping[str, frozenset[int]]
    feasible_windows: Mapping[CandidateDay, tuple[PlanningWindow, ...]]
    preferred_windows: Mapping[str, tuple[PlanningWindow, ...]]
    meal_eligibility: Mapping[MealSlot, tuple[PlanningWindow, ...]]
    related_by_place: Mapping[str, frozenset[str]]
    unknown_opening_ids: frozenset[str]
    unknown_opening_days: Mapping[str, frozenset[int]]
    late_night_eligible_ids: frozenset[str]
    unscheduled_priority: tuple[CandidateExclusion, ...]
    discarded_optional: tuple[CandidateExclusion, ...]
    warnings: tuple[str, ...]
    accommodation_nights: int = 0
    accommodation_cost_per_person_by_id: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    canonical_place_id_by_candidate_id: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
