import asyncio

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.public import build_itinerary_planner_graph
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import (
    FixedCostEstimator,
    GeneratedMatrixProvider,
)
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    continuity_candidates,
)


def test_graph_prepares_new_planner_input() -> None:
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(), FixedCostEstimator()
    )
    planner_input = ItineraryPlannerInput.model_validate(
        payload(
            places=[
                candidate("ho_guom", priority="user_input"),
                *continuity_candidates(),
            ],
            foods=[
                food("breakfast", supported_meals=["breakfast"]),
                food("lunch", supported_meals=["lunch"]),
                food("dinner", supported_meals=["dinner"]),
            ],
        )
    )

    result = asyncio.run(graph.ainvoke({"input": planner_input}))

    assert result.get("error") is None
    assert result["prepared_problem"].candidate_by_id["ho_guom"].name == "Ho Guom"
    assert result["routing_problem"].sparse_arcs
    assert result["optimization_result"].user_input_count == 1
    assert result["output"].destination == "Hanoi"
    assert len(result["output"].days) == 1
    assert len(result["output"].days[0].stops) >= 6
    assert (
        result["output"].solver.objective_policy_version
        == "hybrid-activity-corridor-v2"
    )
    assert result["output"].phase_timings_ms["total"] >= 0


def test_graph_repeats_restaurant_only_after_distinct_matching_is_exhausted() -> None:
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(), FixedCostEstimator()
    )
    planner_input = ItineraryPlannerInput.model_validate(
        payload(
            places=[
                candidate("morning_activity", duration_minutes=60),
                candidate("afternoon_activity", duration_minutes=60),
            ],
            foods=[food("only_restaurant")],
        )
    )

    result = asyncio.run(graph.ainvoke({"input": planner_input}))

    assert result.get("error") is None
    meal_stops = [stop for stop in result["output"].days[0].stops if stop.meal_type]
    assert {stop.meal_type.value for stop in meal_stops} == {
        "breakfast",
        "lunch",
        "dinner",
    }
    assert {stop.place_id for stop in meal_stops} == {"only_restaurant"}
    assert len({stop.item_id for stop in meal_stops}) == 3
    assert all(
        "meal_repeat" not in value
        for leg in result["output"].days[0].legs
        for value in (leg.from_place_id, leg.to_place_id)
    )
    assert any(
        "Repeated restaurant fallback" in warning
        for warning in result["output"].warnings
    )


def test_graph_does_not_inherit_parent_checkpointer() -> None:
    graph = build_itinerary_planner_graph()

    assert graph.checkpointer is False


def test_graph_returns_preflight_error_without_three_meals() -> None:
    graph = build_itinerary_planner_graph()
    raw = payload()
    raw["food"][0]["supportedMeals"] = ["lunch", "dinner"]

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert "breakfast" in result["error"]
    assert result["error_code"] == "missing_meal_coverage"
    assert result["preflight_failure"].model_dump(mode="json") == {
        "code": "missing_meal_coverage",
        "missing": [{"day": 1, "meal": "breakfast"}],
    }
    assert "prepared_problem" not in result
