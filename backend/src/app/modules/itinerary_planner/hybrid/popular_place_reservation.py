from __future__ import annotations

from math import ceil

from app.modules.itinerary_planner.optimizer.popular_place_coverage import (
    POPULAR_PLACES_PER_DAY,
)
from app.modules.itinerary_planner.optimizer.special_place_coverage import (
    SPECIAL_PLACES_PER_DAY,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


def available_candidate_ids(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    popular_ids: frozenset[str],
    special_ids: frozenset[str],
) -> set[str]:
    daily_popular = _group_candidates_for_day(
        problem,
        day=day,
        used_ids=used_ids,
        candidate_ids=popular_ids,
        per_day=POPULAR_PLACES_PER_DAY,
    )
    daily_special = _group_candidates_for_day(
        problem,
        day=day,
        used_ids=used_ids,
        candidate_ids=special_ids,
        per_day=SPECIAL_PLACES_PER_DAY,
    )
    controlled = popular_ids | special_ids
    daily_controlled = daily_popular | daily_special
    available = {
        candidate_id
        for candidate_id, preferred in problem.preferred_days.items()
        if day in preferred
        and candidate_id not in used_ids
        and (candidate_id not in controlled or candidate_id in daily_controlled)
    }
    available.update(daily_controlled)
    return available


def _group_candidates_for_day(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    candidate_ids: frozenset[str],
    per_day: int,
) -> frozenset[str]:
    """Expose a fair daily share while reserving valued places for later days."""
    remaining = candidate_ids - used_ids
    days_left = problem.trip.days - day + 1
    daily_share = min(
        per_day,
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
