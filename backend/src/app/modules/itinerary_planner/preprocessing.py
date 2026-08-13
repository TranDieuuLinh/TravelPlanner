from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    ItineraryPlannerInput,
    MealType,
    PlannerCandidate,
    PlannerFoodCandidate,
    PlannerTrip,
)
from app.modules.itinerary_planner.policies import MEAL_POLICIES
from app.modules.itinerary_planner.time_windows import (
    PlanningWindow,
    feasible_start_window,
    full_itinerary_window,
    normalize_and_merge,
    windows_fitting_duration,
)


PRIORITY_CANDIDATES = {CandidatePriority.user_input, CandidatePriority.url}


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


Candidate = PlannerCandidate | PlannerFoodCandidate
CandidateDay = tuple[str, int]
MealSlot = tuple[str, int, MealType]


@dataclass(frozen=True, slots=True)
class PreparedPlanningProblem:
    trip: PlannerTrip
    valid_places: tuple[PlannerCandidate, ...]
    valid_food: tuple[PlannerFoodCandidate, ...]
    candidate_by_id: Mapping[str, Candidate]
    feasible_days: Mapping[str, frozenset[int]]
    feasible_windows: Mapping[CandidateDay, tuple[PlanningWindow, ...]]
    preferred_windows: Mapping[str, tuple[PlanningWindow, ...]]
    meal_eligibility: Mapping[MealSlot, tuple[PlanningWindow, ...]]
    related_by_place: Mapping[str, frozenset[str]]
    unknown_opening_ids: frozenset[str]
    unknown_opening_days: Mapping[str, frozenset[int]]
    unscheduled_priority: tuple[CandidateExclusion, ...]
    discarded_optional: tuple[CandidateExclusion, ...]
    warnings: tuple[str, ...]


def normalize_tag(value: str) -> str:
    normalized = re.sub(r"[^\w]+", "_", value.strip().casefold(), flags=re.UNICODE)
    return normalized.strip("_")


def normalize_tags(values: list[str]) -> list[str]:
    normalized = (normalize_tag(value) for value in values)
    return list(dict.fromkeys(value for value in normalized if value))


def _opening_windows(
    candidate: Candidate,
    day: int,
) -> tuple[tuple[PlanningWindow, ...], bool]:
    if candidate.opening_hours is None:
        return full_itinerary_window(), True
    intervals = candidate.opening_hours.get(str(day))
    if intervals is None:
        return full_itinerary_window(), True
    return normalize_and_merge(intervals), False


def _exclusion(
    candidate: Candidate,
    reason_code: str,
    message: str,
) -> CandidateExclusion:
    return CandidateExclusion(
        place_id=candidate.place_id,
        name=candidate.name,
        priority=candidate.priority,
        reason_code=reason_code,
        message=message,
    )


def _store_exclusion(
    exclusion: CandidateExclusion,
    unscheduled: list[CandidateExclusion],
    discarded: list[CandidateExclusion],
) -> None:
    if exclusion.priority in PRIORITY_CANDIDATES:
        unscheduled.append(exclusion)
    else:
        discarded.append(exclusion)


def _prepare_place(
    candidate: PlannerCandidate,
    trip: PlannerTrip,
) -> tuple[
    PlannerCandidate,
    dict[int, tuple[PlanningWindow, ...]],
    frozenset[int],
    CandidateExclusion | None,
]:
    normalized = candidate.model_copy(update={"tags": normalize_tags(candidate.tags)})
    if normalized.price.currency != trip.budget.currency:
        return normalized, {}, frozenset(), _exclusion(
            normalized,
            "currency_mismatch",
            "Candidate price currency does not match the trip budget currency.",
        )

    feasible: dict[int, tuple[PlanningWindow, ...]] = {}
    unknown_days: set[int] = set()
    had_open_window = False
    for day in range(1, trip.days + 1):
        opening, unknown = _opening_windows(normalized, day)
        unknown_days.update({day} if unknown else set())
        had_open_window = had_open_window or bool(opening)
        fitting = windows_fitting_duration(opening, normalized.duration_minutes)
        if fitting:
            feasible[day] = fitting

    if feasible:
        return normalized, feasible, frozenset(unknown_days), None
    if not had_open_window:
        reason = "closed_for_entire_trip"
        message = "Candidate is closed for every trip day."
    else:
        reason = "duration_exceeds_every_opening_window"
        message = "No opening window can contain the full visit duration."
    return normalized, {}, frozenset(unknown_days), _exclusion(
        normalized, reason, message
    )


def _prepare_food(
    candidate: PlannerFoodCandidate,
    trip: PlannerTrip,
) -> tuple[
    PlannerFoodCandidate,
    dict[int, tuple[PlanningWindow, ...]],
    dict[tuple[int, MealType], tuple[PlanningWindow, ...]],
    frozenset[int],
    CandidateExclusion | None,
]:
    normalized = candidate.model_copy(update={"tags": normalize_tags(candidate.tags)})
    if normalized.price.currency != trip.budget.currency:
        return normalized, {}, {}, frozenset(), _exclusion(
            normalized,
            "currency_mismatch",
            "Food price currency does not match the trip budget currency.",
        )

    day_windows: dict[int, tuple[PlanningWindow, ...]] = {}
    eligibility: dict[tuple[int, MealType], tuple[PlanningWindow, ...]] = {}
    unknown_days: set[int] = set()
    for day in range(1, trip.days + 1):
        opening, unknown = _opening_windows(normalized, day)
        unknown_days.update({day} if unknown else set())
        if opening:
            day_windows[day] = opening
        for meal in normalized.supported_meals:
            policy = MEAL_POLICIES[meal]
            starts = tuple(
                start_window
                for window in opening
                if (
                    start_window := feasible_start_window(
                        window,
                        policy.earliest_start,
                        policy.latest_start,
                        policy.duration_minutes,
                    )
                )
                is not None
            )
            if starts:
                eligibility[(day, meal)] = starts

    if eligibility:
        return normalized, day_windows, eligibility, frozenset(unknown_days), None
    return normalized, {}, {}, frozenset(unknown_days), _exclusion(
        normalized,
        "unsupported_meal_coverage",
        "Food is not open for any supported meal window during the trip.",
    )


def prepare_planning_problem(payload: ItineraryPlannerInput) -> PreparedPlanningProblem:
    trip = payload.trip.model_copy(
        update={"preferences": normalize_tags(payload.trip.preferences)}
    )
    valid_places: list[PlannerCandidate] = []
    valid_food: list[PlannerFoodCandidate] = []
    feasible_days: dict[str, frozenset[int]] = {}
    feasible_windows: dict[CandidateDay, tuple[PlanningWindow, ...]] = {}
    meal_eligibility: dict[MealSlot, tuple[PlanningWindow, ...]] = {}
    unknown_days_by_id: dict[str, frozenset[int]] = {}
    unscheduled: list[CandidateExclusion] = []
    discarded: list[CandidateExclusion] = []
    warnings = list(payload.upstream_warnings)

    for candidate in payload.places:
        normalized, windows, unknown_days, exclusion = _prepare_place(candidate, trip)
        if exclusion:
            _store_exclusion(exclusion, unscheduled, discarded)
            continue
        valid_places.append(normalized)
        feasible_days[normalized.place_id] = frozenset(windows)
        feasible_windows.update(
            {(normalized.place_id, day): value for day, value in windows.items()}
        )
        if unknown_days:
            unknown_days_by_id[normalized.place_id] = unknown_days

    for candidate in payload.food:
        normalized, windows, eligibility, unknown_days, exclusion = _prepare_food(
            candidate, trip
        )
        if exclusion:
            _store_exclusion(exclusion, unscheduled, discarded)
            continue
        valid_food.append(normalized)
        feasible_days[normalized.place_id] = frozenset(windows)
        feasible_windows.update(
            {(normalized.place_id, day): value for day, value in windows.items()}
        )
        meal_eligibility.update(
            {
                (normalized.place_id, day, meal): value
                for (day, meal), value in eligibility.items()
            }
        )
        if unknown_days:
            unknown_days_by_id[normalized.place_id] = unknown_days

    candidates: list[Candidate] = [*valid_places, *valid_food]
    candidate_by_id = {candidate.place_id: candidate for candidate in candidates}
    related_by_place: dict[str, frozenset[str]] = {}
    for candidate in candidates:
        valid_targets = {
            target
            for target in candidate.relationships
            if target in candidate_by_id and target != candidate.place_id
        }
        invalid_targets = set(candidate.relationships) - valid_targets
        if invalid_targets:
            warnings.append(
                f"Ignored dangling relationships from {candidate.place_id}: "
                + ", ".join(sorted(invalid_targets))
            )
        related_by_place[candidate.place_id] = frozenset(valid_targets)

    for place_id in unknown_days_by_id:
        warnings.append(
            f"openingHours is unknown for {place_id}; treated as open for the "
            "full itinerary window on affected days."
        )

    missing_meals = tuple(
        MissingMealCoverage(day, meal)
        for day in range(1, trip.days + 1)
        for meal in MealType
        if not any(
            (food.place_id, day, meal) in meal_eligibility for food in valid_food
        )
    )
    if missing_meals:
        raise PlanningPreflightError(missing_meals)

    preferred_windows = {
        candidate.place_id: normalize_and_merge(candidate.preferred_time_windows)
        for candidate in candidates
    }
    return PreparedPlanningProblem(
        trip=trip,
        valid_places=tuple(valid_places),
        valid_food=tuple(valid_food),
        candidate_by_id=MappingProxyType(candidate_by_id),
        feasible_days=MappingProxyType(feasible_days),
        feasible_windows=MappingProxyType(feasible_windows),
        preferred_windows=MappingProxyType(preferred_windows),
        meal_eligibility=MappingProxyType(meal_eligibility),
        related_by_place=MappingProxyType(related_by_place),
        unknown_opening_ids=frozenset(unknown_days_by_id),
        unknown_opening_days=MappingProxyType(unknown_days_by_id),
        unscheduled_priority=tuple(unscheduled),
        discarded_optional=tuple(discarded),
        warnings=tuple(warnings),
    )
