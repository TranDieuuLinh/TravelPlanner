from __future__ import annotations

from collections.abc import Callable

from app.modules.place_checker.food_pool_policy import RestaurantAggregate
from app.modules.place_checker.food_selection_contract import (
    FoodMealCoverage,
    FoodMealSlot,
    FoodMealSlotAssignment,
)
from app.modules.place_checker.planning_time_windows import meals_for_hours

MEALS = ("breakfast", "lunch", "dinner")
MealSlotKey = tuple[int, str]
AggregateRank = Callable[[RestaurantAggregate], tuple]


def build_food_meal_coverage(
    candidates: list[RestaurantAggregate],
    days: int,
    rank: AggregateRank,
) -> FoodMealCoverage:
    ordered = sorted(candidates, key=rank, reverse=True)
    hard = _maximum_matching(ordered, days, excluded_ids=frozenset())
    hard_ids = frozenset(hard.values())
    reserve = _maximum_matching(ordered, days, excluded_ids=hard_ids)
    slots = _slots(days)
    return FoodMealCoverage(
        days=days,
        hard_complete=len(hard) == len(slots),
        reserve_complete=len(reserve) == len(slots),
        hard_assignments=_assignments(hard),
        hard_missing_slots=_missing(slots, hard),
        reserve_assignments=_assignments(reserve),
        reserve_missing_slots=_missing(slots, reserve),
    )


def matched_restaurant_ids(coverage: FoodMealCoverage) -> set[str]:
    return {
        item.restaurant_id
        for item in [
            *coverage.hard_assignments,
            *coverage.reserve_assignments,
        ]
    }


def missing_meals(coverage: FoodMealCoverage) -> list[str]:
    return list(
        dict.fromkeys(
            slot.meal
            for slot in [
                *coverage.hard_missing_slots,
                *coverage.reserve_missing_slots,
            ]
        )
    )


def _maximum_matching(
    candidates: list[RestaurantAggregate],
    days: int,
    *,
    excluded_ids: frozenset[str],
) -> dict[MealSlotKey, str]:
    slots = _slots(days)
    options = {
        slot: [
            item.best.restaurant_id
            for item in candidates
            if item.best.restaurant_id not in excluded_ids
            and slot[1] in meals_for_hours(item.best.metadata.opening_hours)
        ]
        for slot in slots
    }
    restaurant_slot: dict[str, MealSlotKey] = {}
    assignment: dict[MealSlotKey, str] = {}

    def assign(slot: MealSlotKey, seen: set[str]) -> bool:
        for restaurant_id in options[slot]:
            if restaurant_id in seen:
                continue
            seen.add(restaurant_id)
            occupied = restaurant_slot.get(restaurant_id)
            if occupied is None or assign(occupied, seen):
                restaurant_slot[restaurant_id] = slot
                assignment[slot] = restaurant_id
                return True
        return False

    for slot in sorted(
        slots,
        key=lambda item: (len(options[item]), item[0], MEALS.index(item[1])),
    ):
        assign(slot, set())
    return assignment


def _slots(days: int) -> list[MealSlotKey]:
    return [(day, meal) for day in range(1, days + 1) for meal in MEALS]


def _assignments(
    values: dict[MealSlotKey, str],
) -> list[FoodMealSlotAssignment]:
    return [
        FoodMealSlotAssignment(day=day, meal=meal, restaurant_id=restaurant_id)
        for (day, meal), restaurant_id in sorted(
            values.items(),
            key=lambda item: (item[0][0], MEALS.index(item[0][1])),
        )
    ]


def _missing(
    slots: list[MealSlotKey],
    values: dict[MealSlotKey, str],
) -> list[FoodMealSlot]:
    return [
        FoodMealSlot(day=day, meal=meal)
        for day, meal in slots
        if (day, meal) not in values
    ]
