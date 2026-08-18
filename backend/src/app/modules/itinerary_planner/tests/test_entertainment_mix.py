from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.entertainment_mix import (
    build_daytime_entertainment_excess_cost,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


def _solve(*, force_entertainment_morning: bool) -> tuple[int, int]:
    model = cp_model.CpModel()
    variables = PlannerVariables()
    for candidate_id in ("museum", "arcade"):
        assigned = variables.remember(model.NewBoolVar(f"assigned:{candidate_id}:1"))
        start = variables.remember(model.NewIntVar(0, 1_440, f"start:{candidate_id}:1"))
        end = variables.remember(model.NewIntVar(0, 1_440, f"end:{candidate_id}:1"))
        variables.assigned[(candidate_id, 1)] = assigned
        variables.start[(candidate_id, 1)] = start
        variables.end[(candidate_id, 1)] = end
        model.Add(assigned == 1)
    model.Add(variables.start[("museum", 1)] == 540)
    model.Add(variables.end[("museum", 1)] == 600)
    model.AddAllowedAssignments(
        [variables.start[("arcade", 1)], variables.end[("arcade", 1)]],
        [(540, 600), (1140, 1200)],
    )
    if force_entertainment_morning:
        model.Add(variables.start[("arcade", 1)] == 540)

    problem = SimpleNamespace(
        trip=SimpleNamespace(days=1),
        valid_places=(SimpleNamespace(place_id="museum"),),
        valid_entertainment=(
            SimpleNamespace(place_id="arcade", entity_type="entertainment"),
        ),
    )
    cost = build_daytime_entertainment_excess_cost(
        model,
        problem,
        variables,
        weight=900,
    )
    model.Minimize(cost)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.Solve(model) == cp_model.OPTIMAL
    return solver.Value(variables.end[("arcade", 1)]), solver.Value(cost)


def test_soft_ten_percent_target_moves_flexible_entertainment_out_of_daytime() -> None:
    entertainment_end, cost = _solve(force_entertainment_morning=False)

    assert entertainment_end == 1200
    assert cost == 0


def test_morning_only_entertainment_remains_feasible_with_excess_cost() -> None:
    entertainment_end, cost = _solve(force_entertainment_morning=True)

    assert entertainment_end == 600
    assert cost == 900
