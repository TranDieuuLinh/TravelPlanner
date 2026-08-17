from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


MORNING_END_MINUTE = 12 * 60
EXPECTED_MORNING_ACTIVITY_SLOTS_PER_DAY = 2
MORNING_ENTERTAINMENT_TARGET_TENTHS = 1


def build_morning_entertainment_excess_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weight: int,
) -> cp_model.LinearExpr:
    """Penalize entertainment above 10% of expected morning activity slots."""
    entertainment_ids = {
        candidate.place_id
        for candidate in problem.valid_entertainment
        if candidate.entity_type == "entertainment"
    }
    if not entertainment_ids:
        return 0

    morning_by_id: dict[tuple[str, int], cp_model.IntVar] = {}
    for (candidate_id, day), assigned in variables.assigned.items():
        if candidate_id not in entertainment_ids:
            continue
        morning = variables.remember(
            model.NewBoolVar(f"morning_activity:{candidate_id}:{day}")
        )
        morning_by_id[(candidate_id, day)] = morning
        model.Add(morning <= assigned)
        start = variables.start[(candidate_id, day)]
        model.Add(start < MORNING_END_MINUTE).OnlyEnforceIf(morning)
        model.Add(start >= MORNING_END_MINUTE).OnlyEnforceIf(
            [assigned, morning.Not()]
        )

    if not morning_by_id:
        return 0

    maximum = len(morning_by_id)
    target = (
        problem.trip.days
        * EXPECTED_MORNING_ACTIVITY_SLOTS_PER_DAY
        * MORNING_ENTERTAINMENT_TARGET_TENTHS
        // 10
    )
    entertainment = sum(morning_by_id.values())
    excess = variables.remember(
        model.NewIntVar(0, maximum, "morning_entertainment_excess")
    )
    model.AddMaxEquality(excess, [entertainment - target, 0])
    return excess * weight
