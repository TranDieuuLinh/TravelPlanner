from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


DAYTIME_END_MINUTE = 18 * 60
EXPECTED_DAYTIME_ACTIVITY_SLOTS_PER_DAY = 4
DAYTIME_ENTERTAINMENT_TARGET_TENTHS = 1


def build_daytime_entertainment_excess_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weight: int,
) -> cp_model.LinearExpr:
    """Penalize entertainment above 10% of expected morning/afternoon slots."""
    entertainment_ids = {
        candidate.place_id
        for candidate in problem.valid_entertainment
        if candidate.entity_type == "entertainment"
    }
    if not entertainment_ids:
        return 0

    daytime_by_id: dict[tuple[str, int], cp_model.IntVar] = {}
    for (candidate_id, day), assigned in variables.assigned.items():
        if candidate_id not in entertainment_ids:
            continue
        daytime = variables.remember(
            model.NewBoolVar(f"daytime_activity:{candidate_id}:{day}")
        )
        daytime_by_id[(candidate_id, day)] = daytime
        model.Add(daytime <= assigned)
        start = variables.start[(candidate_id, day)]
        model.Add(start < DAYTIME_END_MINUTE).OnlyEnforceIf(daytime)
        model.Add(start >= DAYTIME_END_MINUTE).OnlyEnforceIf(
            [assigned, daytime.Not()]
        )

    if not daytime_by_id:
        return 0

    maximum = len(daytime_by_id)
    target = (
        problem.trip.days
        * EXPECTED_DAYTIME_ACTIVITY_SLOTS_PER_DAY
        * DAYTIME_ENTERTAINMENT_TARGET_TENTHS
        // 10
    )
    entertainment = sum(daytime_by_id.values())
    excess = variables.remember(
        model.NewIntVar(0, maximum, "daytime_entertainment_excess")
    )
    model.AddMaxEquality(excess, [entertainment - target, 0])
    return excess * weight
