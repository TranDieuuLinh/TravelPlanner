from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.config import ObjectiveWeights
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


def build_activity_coverage_value(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weights: ObjectiveWeights,
) -> cp_model.LinearExpr:
    """Reward every feasible real activity; do not impose a daily target."""
    values = []
    for day in range(1, problem.trip.days + 1):
        assignments = [
            variables.assigned[(candidate.place_id, day)]
            for candidate in problem.valid_places
            if (candidate.place_id, day) in variables.assigned
        ]
        if not assignments:
            continue
        values.append(sum(assignments) * weights.activity_coverage)
    return sum(values)
