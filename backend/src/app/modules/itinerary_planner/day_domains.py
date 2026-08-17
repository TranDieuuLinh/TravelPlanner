from __future__ import annotations

from dataclasses import dataclass

from app.modules.itinerary_planner.activity_day_domains import (
    MAX_OPTIONAL_DAYS,
    project_activity_days,
)
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


@dataclass(frozen=True, slots=True)
class DayDomainProjection:
    feasible_days: dict[str, frozenset[int]]
    feasible_windows: dict[CandidateDay, tuple[PlanningWindow, ...]]
    meal_eligibility: dict[MealSlot, tuple[PlanningWindow, ...]]
    restricted_candidate_count: int
    meal_repair_count: int
    fallback_food: tuple[PlannerFoodCandidate, ...] = ()
    meal_aliases: tuple[tuple[str, str], ...] = ()
    reused_meal_slots: tuple[tuple[int, MealType, str], ...] = ()

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
        if self.reused_meal_slots:
            details = ", ".join(
                f"day {day} {meal.value}: {place_id}"
                for day, meal, place_id in self.reused_meal_slots
            )
            values.append(
                "Repeated restaurant fallback was required because the original "
                f"pool has no distinct three-meal matching ({details})."
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
    if days > MAX_OPTIONAL_DAYS and len(places) >= days:
        activity_projection = project_activity_days(
            days=days,
            places=places,
            feasible_days=feasible_days,
        )
        center_by_day = activity_projection.center_by_day
        projected_days = activity_projection.feasible_days
        restricted = sum(
            projected_days[candidate.place_id] != feasible_days[candidate.place_id]
            for candidate in places
        )
    else:
        projected_days = dict(feasible_days)
        center = _pool_medoid([*places, *food])
        center_by_day = {day: center for day in range(1, days + 1)}
        restricted = 0

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
    repair_count, fallback_food, aliases, reused_slots = _repair_meal_coverage(
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
        tuple(fallback_food),
        tuple(aliases.items()),
        tuple(reused_slots),
    )


def _pool_medoid(
    candidates: list[PlannerCandidate | PlannerFoodCandidate],
) -> PlannerCandidate | PlannerFoodCandidate | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            sum(_distance_squared(candidate, other) for other in candidates),
            candidate.place_id,
        ),
    )


def _nearest_feasible_days(
    candidate: PlannerCandidate | PlannerFoodCandidate,
    center_by_day: dict[int, PlannerCandidate | PlannerFoodCandidate],
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
    center_by_day: dict[int, PlannerCandidate | PlannerFoodCandidate | None],
) -> tuple[
    int,
    list[PlannerFoodCandidate],
    dict[str, str],
    list[tuple[int, MealType, str]],
]:
    repairs = 0
    fallback_food: list[PlannerFoodCandidate] = []
    aliases: dict[str, str] = {}
    reused_slots: list[tuple[int, MealType, str]] = []
    for day in range(1, days + 1):
        matching = _unique_meal_matching(
            day=day,
            food=food,
            projected_meals=projected_meals,
            original_meals=original_meals,
            center=center_by_day[day],
        )
        if matching is None:
            aliases_for_day = _repeated_meal_aliases(
                day=day,
                food=food,
                projected_meals=projected_meals,
                original_meals=original_meals,
                center=center_by_day[day],
            )
            for alias, canonical_id, meal in aliases_for_day:
                fallback_food.append(alias)
                aliases[alias.place_id] = canonical_id
                reused_slots.append((day, meal, canonical_id))
                projected_days[alias.place_id] = frozenset({day})
                projected_windows[(alias.place_id, day)] = original_windows[
                    (canonical_id, day)
                ]
                projected_meals[(alias.place_id, day, meal)] = original_meals[
                    (canonical_id, day, meal)
                ]
            continue
        for place_id in set(matching.values()):
            if day in projected_days[place_id]:
                continue
            projected_days[place_id] = frozenset({*projected_days[place_id], day})
            if window := original_windows.get((place_id, day)):
                projected_windows[(place_id, day)] = window
            for supported_meal in MealType:
                key = (place_id, day, supported_meal)
                if key in original_meals:
                    projected_meals[key] = original_meals[key]
            repairs += 1
    return repairs, fallback_food, aliases, reused_slots


def _unique_meal_matching(
    *,
    day: int,
    food: list[PlannerFoodCandidate],
    projected_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    original_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    center: PlannerCandidate | PlannerFoodCandidate | None,
) -> dict[MealType, str] | None:
    """Match each daily meal to a distinct restaurant candidate."""
    options_by_meal = _meal_options(day, food, projected_meals, original_meals, center)
    matching = _maximum_unique_matching(options_by_meal)
    return matching if len(matching) == len(MealType) else None


def _maximum_unique_matching(
    options_by_meal: dict[MealType, list[str]],
) -> dict[MealType, str]:
    meal_by_place: dict[str, MealType] = {}

    def assign(meal: MealType, visited: set[str]) -> bool:
        for place_id in options_by_meal[meal]:
            if place_id in visited:
                continue
            visited.add(place_id)
            previous_meal = meal_by_place.get(place_id)
            if previous_meal is None or assign(previous_meal, visited):
                meal_by_place[place_id] = meal
                return True
        return False

    for meal in sorted(
        MealType, key=lambda item: (len(options_by_meal[item]), item.value)
    ):
        assign(meal, set())
    return {meal: place_id for place_id, meal in meal_by_place.items()}


def _repeated_meal_aliases(
    *,
    day: int,
    food: list[PlannerFoodCandidate],
    projected_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    original_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    center: PlannerCandidate | PlannerFoodCandidate | None,
) -> list[tuple[PlannerFoodCandidate, str, MealType]]:
    candidate_by_id = {candidate.place_id: candidate for candidate in food}
    options = _meal_options(day, food, projected_meals, original_meals, center)
    if any(not values for values in options.values()):
        return []
    assignment = _maximum_unique_matching(options)
    for meal in MealType:
        assignment.setdefault(meal, options[meal][0])
    return [
        (
            candidate_by_id[assignment[meal]].model_copy(
                update={
                    "place_id": f"meal_repeat:{day}:{meal.value}",
                    "supported_meals": [meal],
                }
            ),
            assignment[meal],
            meal,
        )
        for meal in MealType
    ]


def _meal_options(
    day: int,
    food: list[PlannerFoodCandidate],
    projected_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    original_meals: dict[MealSlot, tuple[PlanningWindow, ...]],
    center: PlannerCandidate | PlannerFoodCandidate | None,
) -> dict[MealType, list[str]]:
    candidate_by_id = {candidate.place_id: candidate for candidate in food}
    return {
        meal: sorted(
            (
                candidate.place_id
                for candidate in food
                if (candidate.place_id, day, meal) in original_meals
            ),
            key=lambda place_id: (
                0 if (place_id, day, meal) in projected_meals else 1,
                _distance_to_center(candidate_by_id[place_id], center),
                place_id,
            ),
        )
        for meal in MealType
    }


def _distance_to_center(
    candidate: PlannerCandidate | PlannerFoodCandidate,
    center: PlannerCandidate | PlannerFoodCandidate | None,
) -> float:
    return _distance_squared(candidate, center) if center is not None else 0


def _distance_squared(
    left: PlannerCandidate | PlannerFoodCandidate,
    right: PlannerCandidate | PlannerFoodCandidate,
) -> float:
    latitude = left.coordinates.latitude - right.coordinates.latitude
    longitude = left.coordinates.longitude - right.coordinates.longitude
    return latitude * latitude + longitude * longitude
