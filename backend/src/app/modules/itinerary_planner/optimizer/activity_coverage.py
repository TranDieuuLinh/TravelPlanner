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
    """Reward up to three real activities per day so usable gaps are filled."""
    values = []
    for day in range(1, problem.trip.days + 1):
        assignments = [
            variables.assigned[(candidate.place_id, day)]
            for candidate in problem.valid_places
            if (candidate.place_id, day) in variables.assigned
        ]
        if not assignments:
            continue
        count = variables.remember(
            model.NewIntVar(0, len(assignments), f"activity_count:{day}")
        )
        covered = variables.remember(
            model.NewIntVar(0, min(3, len(assignments)), f"activity_covered:{day}")
        )
        model.Add(count == sum(assignments))
        model.AddMinEquality(covered, [count, 3])
        values.append(covered * weights.activity_coverage)
    return sum(values)
