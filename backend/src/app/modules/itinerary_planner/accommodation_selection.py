from __future__ import annotations

from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.quality import bayesian_adjusted_rating_by_id


BUDGET_AWARE_SOURCES = frozenset({"explicit", "estimated_daily_cost"})


def select_accommodation_anchor_id(
    problem: PreparedPlanningProblem,
) -> str | None:
    """Prefer the cheapest verified option when the trip has a budget target."""
    if not problem.accommodations or not problem.accommodation_nights:
        return None
    if problem.trip.budget.source not in BUDGET_AWARE_SOURCES:
        return problem.accommodations[0].place_id
    bayesian_ratings = bayesian_adjusted_rating_by_id(problem.accommodations)
    return min(
        problem.accommodations,
        key=lambda item: (
            problem.accommodation_cost_per_person_by_id[item.place_id],
            -(bayesian_ratings.get(item.place_id) or 0),
            -(item.review_count or 0),
            item.place_id,
        ),
    ).place_id
