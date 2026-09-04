import asyncio

from app.modules.itinerary_planner.beam_first_graph import (
    build_beam_first_itinerary_planner_graph,
)
from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import (
    FixedCostEstimator,
    GeneratedMatrixProvider,
)


def _planner_input() -> ItineraryPlannerInput:
    return ItineraryPlannerInput.model_validate(
        payload(
            places=[candidate("museum"), candidate("park")],
            foods=[
                food("breakfast", supported_meals=["breakfast"]),
                food("lunch", supported_meals=["lunch"]),
                food("dinner", supported_meals=["dinner"]),
            ],
        )
    )


def test_beam_first_graph_uses_beam_when_complete() -> None:
    provider = GeneratedMatrixProvider()
    graph = build_beam_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )

    result = asyncio.run(graph.ainvoke({"input": _planner_input()}))

    assert result.get("error") is None
    assert result["selected_optimizer"] == "beam_search"
    assert result.get("fallback_used") is not True
    assert provider.calls == 1
    assert result["output"].evaluation is not None


def test_beam_first_graph_reuses_matrix_for_hybrid_fallback() -> None:
    provider = GeneratedMatrixProvider()
    graph = build_beam_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
        beam_config=BeamSearchConfig(time_limit_seconds=0),
    )

    result = asyncio.run(graph.ainvoke({"input": _planner_input()}))

    assert result.get("error") is None
    assert result["selected_optimizer"] == "hybrid_cp_sat"
    assert result["fallback_used"] is True
    assert result["beam_failure_reason"] == "beam_search_deadline"
    assert provider.calls == 1
    assert result["output"].evaluation is None
    assert any(
        "Hybrid planner was used as fallback" in item for item in result["warnings"]
    )


def test_beam_first_graph_does_not_fallback_for_shared_preflight_error() -> None:
    provider = GeneratedMatrixProvider()
    graph = build_beam_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )
    raw = payload()
    raw["food"][0]["supportedMeals"] = ["lunch", "dinner"]

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert result["error_code"] == "missing_meal_coverage"
    assert "selected_optimizer" not in result
    assert provider.calls == 0
