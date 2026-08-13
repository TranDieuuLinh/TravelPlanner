import asyncio

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.public import build_itinerary_planner_graph
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import (
    FixedCostEstimator,
    GeneratedMatrixProvider,
)


def test_graph_prepares_new_planner_input() -> None:
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(), FixedCostEstimator()
    )
    planner_input = ItineraryPlannerInput.model_validate(
        payload(
            places=[candidate("ho_guom", priority="user_input")],
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
    assert len(result["output"].days[0].stops) == 4
    assert result["output"].solver.objective_policy_version
    assert result["output"].phase_timings_ms["total"] >= 0


def test_graph_returns_preflight_error_without_three_meals() -> None:
    graph = build_itinerary_planner_graph()
    raw = payload()
    raw["food"][0]["supportedMeals"] = ["lunch", "dinner"]

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert "breakfast" in result["error"]
    assert "prepared_problem" not in result
