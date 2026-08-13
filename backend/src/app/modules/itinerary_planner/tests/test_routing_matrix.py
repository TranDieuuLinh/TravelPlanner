import asyncio

import pytest

from app.modules.itinerary_planner.adapters.in_memory_matrix import InMemoryMatrixCache
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import build_routing_problem, safe_travel
from app.modules.itinerary_planner.routing_models import MatrixCell
from app.modules.itinerary_planner.routing_models import (
    RoutingErrorCode,
    RoutingPhaseError,
)
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import (
    FixedCostEstimator,
    GeneratedMatrixProvider,
)


def prepared_with_distinct_locations():
    first = candidate("first", priority="user_input")
    second = candidate("second")
    second["coordinates"] = {"latitude": 21.04, "longitude": 105.86}
    meal = food()
    meal["coordinates"] = {"latitude": 21.05, "longitude": 105.87}
    parsed = ItineraryPlannerInput.model_validate(
        payload(places=[first, second], foods=[meal])
    )
    return prepare_planning_problem(parsed)


def test_global_matrix_is_directed_and_cached_once() -> None:
    problem = prepared_with_distinct_locations()
    provider = GeneratedMatrixProvider(asymmetric=True)
    cache = InMemoryMatrixCache()

    first = asyncio.run(
        build_routing_problem(
            problem,
            provider,
            FixedCostEstimator(),
            cache=cache,
            provider_namespace="fake:v1",
        )
    )
    second = asyncio.run(
        build_routing_problem(
            problem,
            provider,
            FixedCostEstimator(),
            cache=cache,
            provider_namespace="fake:v1",
        )
    )

    assert provider.calls == 1
    assert first.matrix.cache_key == second.matrix.cache_key
    assert first.travel_by_candidate_pair[("first", "second")] != (
        first.travel_by_candidate_pair[("second", "first")]
    )


def test_same_coordinates_share_one_matrix_node_but_remain_candidates() -> None:
    first = candidate("normal_visit")
    related = candidate("special_at_same_place")
    meal = food()
    meal["coordinates"] = {"latitude": 21.05, "longitude": 105.87}
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(places=[first, related], foods=[meal])
        )
    )

    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            FixedCostEstimator(),
        )
    )

    assert len(routing.locations) == 2
    assert routing.candidate_to_matrix_node["normal_visit"] == (
        routing.candidate_to_matrix_node["special_at_same_place"]
    )
    assert routing.travel_by_candidate_pair[
        ("normal_visit", "special_at_same_place")
    ].safe_minutes == 0


def test_requires_real_matrix_and_transport_cost_providers() -> None:
    problem = prepared_with_distinct_locations()

    with pytest.raises(RoutingPhaseError) as missing_matrix:
        asyncio.run(build_routing_problem(problem, None, FixedCostEstimator()))
    assert missing_matrix.value.code == RoutingErrorCode.matrix_provider_not_configured

    with pytest.raises(RoutingPhaseError) as missing_cost:
        asyncio.run(build_routing_problem(problem, GeneratedMatrixProvider(), None))
    assert missing_cost.value.code == RoutingErrorCode.transport_cost_not_configured


def test_safe_travel_uses_fixed_and_percentage_buffer() -> None:
    short = safe_travel(
        MatrixCell(600, 2_000, True), FixedCostEstimator(), "auto", 1
    )
    long = safe_travel(
        MatrixCell(3_600, 20_000, True), FixedCostEstimator(), "auto", 1
    )

    assert (short.raw_minutes, short.safe_minutes) == (10, 15)
    assert (long.raw_minutes, long.safe_minutes) == (60, 69)
