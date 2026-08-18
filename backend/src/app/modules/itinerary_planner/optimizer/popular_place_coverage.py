from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.shared.tools.bayesian_rating import bayesian_rating


MIN_POPULAR_REVIEW_COUNT = 500
MIN_POPULAR_BAYESIAN_RATING = 4.2
POPULAR_PLACES_PER_DAY = 2
POPULAR_PRIOR_MEAN = 4.0
POPULAR_PRIOR_WEIGHT = 100.0


def popular_place_ids(problem: PreparedPlanningProblem) -> frozenset[str]:
    """Return high-confidence popular TravelPlaces, excluding leisure/food pools."""
    return frozenset(
        candidate.place_id
        for candidate in problem.valid_places
        if (candidate.review_count or 0) >= MIN_POPULAR_REVIEW_COUNT
        and (
            bayesian_rating(
                rating=candidate.rating,
                review_count=candidate.review_count,
                prior_mean=POPULAR_PRIOR_MEAN,
                prior_weight=POPULAR_PRIOR_WEIGHT,
            )
            or 0
        )
        >= MIN_POPULAR_BAYESIAN_RATING
    )


def build_popular_place_shortfall_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weight: int,
) -> cp_model.LinearExpr:
    popular_ids = popular_place_ids(problem)
    if not popular_ids:
        return 0
    costs = []
    for day in range(1, problem.trip.days + 1):
        feasible = [
            variables.assigned[(candidate_id, day)]
            for candidate_id in popular_ids
            if (candidate_id, day) in variables.assigned
        ]
        if not feasible:
            continue
        target = min(POPULAR_PLACES_PER_DAY, len(feasible))
        shortfall = variables.remember(
            model.NewIntVar(0, target, f"popular_place_shortfall:{day}")
        )
        model.AddMaxEquality(shortfall, [target - sum(feasible), 0])
        costs.append(shortfall * weight)
    return sum(costs)
