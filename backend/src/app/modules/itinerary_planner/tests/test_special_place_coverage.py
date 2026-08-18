from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.special_place_coverage import (
    build_special_place_shortfall_cost,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


def test_two_special_places_per_day_is_a_soft_target() -> None:
    model = cp_model.CpModel()
    variables = PlannerVariables()
    places = tuple(
        SimpleNamespace(place_id=f"special_{index}", source_kind="special_experience")
        for index in range(2)
    )
    for candidate in places:
        assigned = variables.remember(
            model.NewBoolVar(f"assigned:{candidate.place_id}:1")
        )
        variables.assigned[(candidate.place_id, 1)] = assigned
    model.Add(variables.assigned[("special_0", 1)] == 1)
    model.Add(variables.assigned[("special_1", 1)] == 0)
    problem = SimpleNamespace(
        trip=SimpleNamespace(days=1),
        valid_places=places,
    )

    cost = build_special_place_shortfall_cost(
        model, problem, variables, weight=4_000
    )
    model.Minimize(cost)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.Solve(model) == cp_model.OPTIMAL
    assert solver.Value(cost) == 4_000
