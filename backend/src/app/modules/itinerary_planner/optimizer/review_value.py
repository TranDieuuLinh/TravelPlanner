from app.modules.itinerary_planner.optimizer.config import ObjectiveWeights
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.quality import (
    bayesian_quality_by_id,
    popularity_by_id,
)


def build_quality_value(
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weights: ObjectiveWeights,
):
    quality_by_id = bayesian_quality_by_id(problem.candidate_by_id.values())
    return sum(
        variables.selected[candidate_id]
        * round(quality_by_id[candidate_id] * weights.quality_max)
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate.rating is not None
    )


def build_popularity_value(
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weights: ObjectiveWeights,
):
    popularity = popularity_by_id(problem.candidate_by_id.values())
    return sum(
        variables.selected[candidate_id]
        * round(popularity[candidate_id] * weights.popularity_max)
        for candidate_id in problem.candidate_by_id
    )
