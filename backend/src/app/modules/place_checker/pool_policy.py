from __future__ import annotations

import math


ACTIVITY_CANDIDATES_PER_DAY = 14
FOOD_CANDIDATES_PER_DAY = 12
ENTERTAINMENT_CANDIDATES_PER_DAY = 4
MAX_ACTIVITY_POOL_TARGET = 420
MAX_FOOD_POOL_TARGET = 300
MAX_ENTERTAINMENT_POOL_TARGET = 120
MAX_QUERY_LIMIT = 60
ACCOMMODATION_POOL_TARGET = 5
MEALS_PER_DAY = 3


def activity_pool_target_for_days(days: int) -> int:
    """Return the TravelPlace reserve required for the trip duration."""
    return min(MAX_ACTIVITY_POOL_TARGET, max(14, days * ACTIVITY_CANDIDATES_PER_DAY))


def food_pool_target_for_days(days: int) -> int:
    """Return the restaurant reserve target, separate from activity capacity."""
    return min(MAX_FOOD_POOL_TARGET, max(10, days * FOOD_CANDIDATES_PER_DAY))


def entertainment_pool_target_for_days(days: int) -> int:
    """Return the optional DrinkDessert/Entertainment reserve target."""
    return min(
        MAX_ENTERTAINMENT_POOL_TARGET,
        max(4, days * ENTERTAINMENT_CANDIDATES_PER_DAY),
    )


def planner_pool_shortfall(
    *,
    days: int,
    travel_place_count: int,
    food_count: int,
    food_meal_counts: dict[str, int] | None = None,
) -> tuple[int, int, int, int]:
    """Return activity-reserve and hard meal-coverage shortfalls."""
    travel_target = activity_pool_target_for_days(days)
    food_target = max(MEALS_PER_DAY, days * MEALS_PER_DAY)
    meal_shortfall = max(
        (max(0, days - count) for count in (food_meal_counts or {}).values()),
        default=0,
    )
    return (
        travel_target,
        food_target,
        max(0, travel_target - travel_place_count),
        max(max(0, food_target - food_count), meal_shortfall),
    )


def combined_pool_target_for_days(days: int) -> int:
    return (
        activity_pool_target_for_days(days)
        + food_pool_target_for_days(days)
        + entertainment_pool_target_for_days(days)
        + ACCOMMODATION_POOL_TARGET
    )


def pool_query_limit_for_days(days: int) -> int:
    """Over-fetch per query; multiple discovery gaps can fill the trip pool."""
    return min(MAX_QUERY_LIMIT, activity_pool_target_for_days(days) * 2)


def per_gap_pool_target(days: int, discovery_gap_count: int) -> int:
    target = activity_pool_target_for_days(days)
    return min(20, max(4, math.ceil(target / max(1, discovery_gap_count))))
