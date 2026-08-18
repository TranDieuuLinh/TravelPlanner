from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    CandidateSourceKind,
)
from app.modules.itinerary_planner.optimizer.evening_entertainment import (
    build_evening_entertainment_policy,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


def _candidate(
    place_id: str,
    source_kind: CandidateSourceKind,
    *,
    entity_type: str = "entertainment",
):
    return SimpleNamespace(
        place_id=place_id,
        name=place_id,
        tags=[],
        source_kind=source_kind,
        entity_type=entity_type,
        priority=CandidatePriority.special_near,
    )


def test_evening_entertainment_is_rewarded_when_no_special_is_selected() -> None:
    model = cp_model.CpModel()
    variables = PlannerVariables()
    assigned = variables.remember(model.NewBoolVar("assigned:arcade:1"))
    start = variables.remember(model.NewIntVar(0, 1_440, "start:arcade:1"))
    variables.assigned[("arcade", 1)] = assigned
    variables.start[("arcade", 1)] = start
    model.Add(assigned == 1)
    model.AddAllowedAssignments([start], [(600,), (1_140,)])
    problem = SimpleNamespace(
        trip=SimpleNamespace(days=1),
            # DrinkDessert is a valid evening leisure fallback even when its
            # relationship provenance is marked as a special source.
        valid_entertainment=(
            _candidate(
                "arcade",
                CandidateSourceKind.special_experience,
                entity_type="drink_dessert",
            ),
        ),
        valid_places=(),
    )

    policy = build_evening_entertainment_policy(
        model,
        problem,
        variables,
        special_weight=9_000,
        fallback_weight=2_500,
        conflict_weight=6_000,
    )
    model.Maximize(policy.fallback_value - policy.special_conflict_cost)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.num_search_workers = 1

    assert solver.Solve(model) == cp_model.OPTIMAL
    assert solver.Value(start) == 1_140
    assert solver.Value(policy.fallback_value) == 2_500


def test_special_evening_suppresses_optional_entertainment() -> None:
    model = cp_model.CpModel()
    variables = PlannerVariables()
    entertainment = variables.remember(model.NewBoolVar("assigned:arcade:1"))
    entertainment_start = variables.remember(
        model.NewIntVar(0, 1_140, "start:arcade:1")
    )
    variables.assigned[("arcade", 1)] = entertainment
    variables.start[("arcade", 1)] = entertainment_start
    model.Add(entertainment_start == 1_140).OnlyEnforceIf(entertainment)
    model.Add(entertainment_start == 0).OnlyEnforceIf(entertainment.Not())
    special = variables.remember(model.NewBoolVar("assigned:water_puppet:1"))
    special_start = variables.remember(
        model.NewIntVar(1_140, 1_140, "start:water_puppet:1")
    )
    variables.assigned[("water_puppet", 1)] = special
    variables.start[("water_puppet", 1)] = special_start
    model.Add(special == 1)
    problem = SimpleNamespace(
        trip=SimpleNamespace(days=1),
        valid_entertainment=(_candidate("arcade", CandidateSourceKind.generic),),
        valid_places=(
            _candidate("water_puppet", CandidateSourceKind.special_experience),
        ),
    )

    policy = build_evening_entertainment_policy(
        model,
        problem,
        variables,
        special_weight=9_000,
        fallback_weight=2_500,
        conflict_weight=6_000,
    )
    model.Maximize(policy.fallback_value - policy.special_conflict_cost)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.num_search_workers = 1

    assert solver.Solve(model) == cp_model.OPTIMAL
    assert solver.Value(entertainment) == 0
    assert solver.Value(policy.special_value) == 9_000
