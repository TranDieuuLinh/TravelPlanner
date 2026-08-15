from __future__ import annotations

from dataclasses import dataclass

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    MealType,
    PlannerCandidate,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.time_windows import PlanningWindow

CandidateDay = tuple[str, int]
MealSlot = tuple[str, int, MealType]
PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}
MAX_OPTIONAL_DAYS = 2


@dataclass(frozen=True, slots=True)
class DayDomainProjection:
    feasible_days: dict[str, frozenset[int]]
    feasible_windows: dict[CandidateDay, tuple[PlanningWindow, ...]]
    meal_eligibility: dict[MealSlot, tuple[PlanningWindow, ...]]
    restricted_candidate_count: int
    meal_repair_count: int

    @property
    def warnings(self) -> tuple[str, ...]:
        values = []
        if self.restricted_candidate_count:
            values.append(
                "Geographic day-domain projection restricted "
                f"{self.restricted_candidate_count} optional candidates to at most "
                "two nearby trip days."
            )
        if self.meal_repair_count:
            values.append(
                "Geographic day-domain projection restored "
                f"{self.meal_repair_count} food-day assignments to preserve meal coverage."
            )
        return tuple(values)


def project_optional_day_domains(
    *,
    days: int,
    places: list[PlannerCandidate],
    food: list[PlannerFoodCandidate],
    feasible_days: dict[str, frozenset[int]],
    feasible_windows: dict[CandidateDay, tuple[PlanningWindow, ...]],
    meal_eligibility: dict[MealSlot, tuple[PlanningWindow, ...]],
) -> DayDomainProjection:
    """Restrict optional candidates geographically while preserving meal coverage."""
    if days <= MAX_OPTIONAL_DAYS or len(places) < days:
        return DayDomainProjection(
            dict(feasible_days),
            dict(feasible_windows),
            dict(meal_eligibility),
            0,
            0,
        )

    centers = _farthest_first_centers(places, min(days, len(places)))
    center_by_day = {day: center for day, center in enumerate(centers, 1)}
    projected_days = dict(feasible_days)
    restricted = 0

    for candidate in places:
        if candidate.priority in PRIORITY_VALUES:
            continue
        selected = _nearest_feasible_days(candidate, center_by_day, feasible_days)
        if selected and selected != feasible_days[candidate.place_id]:
            projected_days[candidate.place_id] = selected
            restricted += 1

    place_ids = {candidate.place_id for candidate in places}
    for candidate in food:
        if candidate.priority in PRIORITY_VALUES:
            continue
        related_days = frozenset(
            day
            for related_id in candidate.relationships
            if related_id in place_ids
            for day in projected_days[related_id]
            if day in feasible_days[candidate.place_id]
        )
        selected = related_days or _nearest_feasible_days(
            candidate, center_by_day, feasible_days
        )
        if selected and selected != feasible_days[candidate.place_id]:
            projected_days[candidate.place_id] = selected
            restricted += 1

    projected_windows = {
        key: value
        for key, value in feasible_windows.items()
        if key[1] in projected_days[key[0]]
    }
    projected_meals = {
        key: value
        for key, value in meal_eligibility.items()
        if key[1] in projected_days[key[0]]
    }
    repair_count = _repair_meal_coverage(
        days=days,
        food=food,
        projected_days=projected_days,
        projected_windows=projected_windows,
        projected_meals=projected_meals,
        original_windows=feasible_windows,
        original_meals=meal_eligibility,
        center_by_day=center_by_day,
    )
    return DayDomainProjection(
        projected_days,
        projected_windows,
        projected_meals,
        restricted,
        repair_count,
    )


def _farthest_first_centers(
    candidates: list[PlannerCandidate], count: int
) -> list[PlannerCandidate]:
    ordered = sorted(candidates, key=lambda item: item.place_id)
    centers = [ordered[0]]
    remaining = ordered[1:]
    while remaining and len(centers) < count:
        selected = max(
            remaining,
            key=lambda item: (
                min(_distance_squared(item, center) for center in centers),
                item.place_id,
            ),
        )
        centers.append(selected)
        remaining.remove(selected)
    return centers


def _nearest_feasible_days(
    candidate: PlannerCandidate | PlannerFoodCandidate,
    center_by_day: dict[int, PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
) -> frozenset[int]:
    allowed = feasible_days[candidate.place_id]
    ordered = sorted(
        (day for day in center_by_day if day in allowed),
        key=lambda day: (_distance_squared(candidate, center_by_day[day]), day),
    )
    return frozenset(ordered[:MAX_OPTIONAL_DAYS])


def _repair_meal_coverage(
    *,
    days: int,
    food: list[PlannerFoodCandidate],
    projected_days: dict[str, frozenset[int]],
    projected_windows: dict[CandidateDay, tuple[PlanningWindow, ...]],
    projected_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    original_windows: dict[CandidateDay, tuple[PlanningWindow, ...]],
    original_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    center_by_day: dict[int, PlannerCandidate],
) -> int:
    repairs = 0
    for day in range(1, days + 1):
        for meal in MealType:
            if any(key[1:] == (day, meal) for key in projected_meals):
                continue
            options = [
                candidate
                for candidate in food
                if (candidate.place_id, day, meal) in original_meals
            ]
            if not options:
                continue
            candidate = min(
                options,
                key=lambda item: (
                    _distance_squared(item, center_by_day[day]),
                    item.place_id,
                ),
            )
            place_id = candidate.place_id
            projected_days[place_id] = frozenset({*projected_days[place_id], day})
            if window := original_windows.get((place_id, day)):
                projected_windows[(place_id, day)] = window
            for supported_meal in MealType:
                key = (place_id, day, supported_meal)
                if key in original_meals:
                    projected_meals[key] = original_meals[key]
            repairs += 1
    return repairs


def _distance_squared(
    left: PlannerCandidate | PlannerFoodCandidate,
    right: PlannerCandidate,
) -> float:
    latitude = left.coordinates.latitude - right.coordinates.latitude
    longitude = left.coordinates.longitude - right.coordinates.longitude
    return latitude * latitude + longitude * longitude
