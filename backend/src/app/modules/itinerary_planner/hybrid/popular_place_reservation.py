from __future__ import annotations

from math import ceil

from app.modules.itinerary_planner.optimizer.popular_place_coverage import (
    POPULAR_PLACES_PER_DAY,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


def available_candidate_ids(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    popular_ids: frozenset[str],
) -> set[str]:
    daily_popular = popular_places_for_day(
        problem,
        day=day,
        used_ids=used_ids,
        popular_ids=popular_ids,
    )
    available = {
        candidate_id
        for candidate_id, preferred in problem.preferred_days.items()
        if day in preferred
        and candidate_id not in used_ids
        and (candidate_id not in popular_ids or candidate_id in daily_popular)
    }
    available.update(daily_popular)
    return available


def popular_places_for_day(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    popular_ids: frozenset[str],
) -> frozenset[str]:
    """Expose a fair daily share while reserving landmarks for later days."""
    remaining = popular_ids - used_ids
    days_left = problem.trip.days - day + 1
    daily_share = min(
        POPULAR_PLACES_PER_DAY,
        ceil(len(remaining) / days_left),
    )
    feasible_now = [
        candidate_id
        for candidate_id in remaining
        if day in problem.feasible_days[candidate_id]
    ]
    ranked = sorted(
        feasible_now,
        key=lambda candidate_id: (
            not _is_last_feasible_day(problem, candidate_id, day),
            day not in problem.preferred_days[candidate_id],
            -(problem.candidate_by_id[candidate_id].review_count or 0),
            -(problem.candidate_by_id[candidate_id].rating or 0),
            candidate_id,
        ),
    )
    urgent_count = sum(
        _is_last_feasible_day(problem, candidate_id, day)
        for candidate_id in feasible_now
    )
    return frozenset(ranked[: max(daily_share, urgent_count)])


def _is_last_feasible_day(
    problem: PreparedPlanningProblem,
    candidate_id: str,
    day: int,
) -> bool:
    return not any(
        feasible_day > day
        for feasible_day in problem.feasible_days[candidate_id]
    )
