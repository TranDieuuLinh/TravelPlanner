from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import CandidateSourceKind
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


SPECIAL_PLACES_PER_DAY = 2


def build_special_place_shortfall_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weight: int,
) -> cp_model.LinearExpr:
    special_ids = {
        candidate.place_id
        for candidate in problem.valid_places
        if candidate.source_kind
        in {CandidateSourceKind.special_experience, CandidateSourceKind.both}
    }
    costs = []
    for day in range(1, problem.trip.days + 1):
        feasible = [
            variables.assigned[(candidate_id, day)]
            for candidate_id in special_ids
            if (candidate_id, day) in variables.assigned
        ]
        if not feasible:
            continue
        target = min(SPECIAL_PLACES_PER_DAY, len(feasible))
        shortfall = variables.remember(
            model.NewIntVar(0, target, f"special_place_shortfall:{day}")
        )
        model.AddMaxEquality(shortfall, [target - sum(feasible), 0])
        costs.append(shortfall * weight)
    return sum(costs)
