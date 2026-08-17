from __future__ import annotations

from math import ceil
from typing import Iterable

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.contract import (
    FoodVenueType,
    PlannerCandidate,
    PlannerEntertainmentCandidate,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.time_windows import PlanningWindow


def is_restaurant(candidate: PlannerCandidate) -> bool:
    return isinstance(candidate, PlannerFoodCandidate) and (
        candidate.venue_type == FoodVenueType.restaurant
    )


def is_drink_dessert(candidate: PlannerCandidate) -> bool:
    return (
        isinstance(candidate, PlannerFoodCandidate)
        and candidate.venue_type == FoodVenueType.drink_dessert
    ) or (
        isinstance(candidate, PlannerEntertainmentCandidate)
        and candidate.entity_type == "drink_dessert"
    )


def is_entertainment(candidate: PlannerCandidate) -> bool:
    return isinstance(candidate, PlannerEntertainmentCandidate) and (
        candidate.entity_type == "entertainment"
    )


def is_travelplace(candidate: PlannerCandidate) -> bool:
    """Return true for a normal travel place, excluding food and leisure items."""
    return not isinstance(candidate, (PlannerFoodCandidate, PlannerEntertainmentCandidate))


def is_restaurant_to_restaurant(
    origin: PlannerCandidate,
    destination: PlannerCandidate,
) -> bool:
    return is_restaurant(origin) and is_restaurant(destination)


def fit_transition_window(
    arrival_minute: int,
    duration_minutes: int,
    windows: Iterable[PlanningWindow | tuple[int, int]],
    max_wait_minutes: int,
) -> tuple[int, int] | None:
    """Return the earliest valid [start, end] or reject the transition."""
    for window in windows:
        start_window = (
            window.start_minute if isinstance(window, PlanningWindow) else window[0]
        )
        end_window = (
            window.end_minute if isinstance(window, PlanningWindow) else window[1]
        )
        start = max(arrival_minute, start_window)
        end = start + duration_minutes
        if end <= end_window and start - arrival_minute <= max_wait_minutes:
            return start, end
    return None


def upper_quartile(
    values: Iterable[int | float], quantile: float = 0.75
) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if not 0 < quantile <= 1:
        raise ValueError("quantile must be in the interval (0, 1]")
    return float(ordered[max(0, ceil(len(ordered) * quantile) - 1)])


def long_transition_allowed(
    *,
    distance_meters: int,
    distance_q3: float | None,
    rating: float | None,
    review_count: int | None,
    review_q3: float | None,
    config: BeamSearchConfig,
) -> bool:
    if distance_q3 is None or distance_meters < distance_q3:
        return True
    return (
        rating is not None
        and rating >= config.long_distance_rating_min
        and review_count is not None
        and review_q3 is not None
        and review_count >= review_q3
    )
