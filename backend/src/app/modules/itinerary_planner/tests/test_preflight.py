from dataclasses import replace

import pytest

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.preflight import (
    ProjectedPoolPreflightError,
    validate_projected_pool,
    validate_routing_connectivity,
)
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing_models import RoutingProblem, TravelMatrix
from app.modules.itinerary_planner.tests.factories import candidate, food, payload


def _viable_problem():
    return prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(
                places=[candidate("activity_1"), candidate("activity_2")],
                foods=[
                    food("breakfast", supported_meals=["breakfast"]),
                    food("lunch", supported_meals=["lunch"]),
                    food("dinner", supported_meals=["dinner"]),
                ],
            )
        )
    )


def test_projected_pool_preflight_rejects_missing_candidate_window() -> None:
    problem = _viable_problem()
    windows = dict(problem.feasible_windows)
    windows.pop(("activity_1", 1))

    with pytest.raises(ProjectedPoolPreflightError) as error:
        validate_projected_pool(replace(problem, feasible_windows=windows))

    assert [(item.code, item.candidate_id) for item in error.value.violations] == [
        ("missing_candidate_window", "activity_1")
    ]


def test_projected_pool_allows_small_preferred_pool_when_reserve_is_feasible() -> None:
    problem = _viable_problem()
    preferred = dict(problem.preferred_days)
    preferred["activity_2"] = frozenset()

    validate_projected_pool(replace(problem, preferred_days=preferred))


def test_projected_pool_requires_two_places_in_full_feasible_reserve() -> None:
    problem = _viable_problem()
    feasible = dict(problem.feasible_days)
    feasible["activity_2"] = frozenset()

    with pytest.raises(ProjectedPoolPreflightError) as error:
        validate_projected_pool(replace(problem, feasible_days=feasible))

    assert [(item.code, item.available) for item in error.value.violations] == [
        ("insufficient_activity_separators", 1)
    ]


def test_routing_connectivity_preflight_rejects_disconnected_pool() -> None:
    problem = _viable_problem()
    routing = RoutingProblem(
        locations=(),
        candidate_to_matrix_node={},
        matrix_node_to_candidates={},
        matrix=TravelMatrix(
            node_ids=(),
            cells=(),
            profile="pedestrian",
            provider="test",
            provider_version="1",
        ),
        travel_by_candidate_pair={},
        sparse_arcs=(),
        neighbor_limit=0,
        warnings=(),
    )

    with pytest.raises(ProjectedPoolPreflightError) as error:
        validate_routing_connectivity(problem, routing)

    assert [(item.code, item.day) for item in error.value.violations] == [
        ("insufficient_routing_connectivity", 1)
    ]
