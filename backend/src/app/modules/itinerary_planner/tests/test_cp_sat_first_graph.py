import asyncio

from app.modules.itinerary_planner import cp_sat_first_graph as graph_module
from app.modules.itinerary_planner import nodes
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.cp_sat_first_graph import (
    build_cp_sat_first_itinerary_planner_graph,
)
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
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


def test_cp_sat_first_graph_uses_cp_sat_when_complete() -> None:
    provider = GeneratedMatrixProvider()
    graph = build_cp_sat_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )

    result = asyncio.run(graph.ainvoke({"input": _planner_input()}))

    assert result.get("error") is None
    assert result["selected_optimizer"] == "hybrid_cp_sat"
    assert result.get("fallback_used") is not True
    assert provider.calls == 1
    assert result["output"].evaluation is None


def test_cp_sat_first_graph_reuses_matrix_for_beam_fallback(monkeypatch) -> None:
    provider = GeneratedMatrixProvider()

    def fail_cp_sat(*args, **kwargs):
        raise OptimizationError("UNKNOWN", "priority")

    monkeypatch.setattr(nodes, "optimize_hybrid_itinerary", fail_cp_sat)
    graph = build_cp_sat_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )

    result = asyncio.run(graph.ainvoke({"input": _planner_input()}))

    assert result.get("error") is None
    assert result["selected_optimizer"] == "beam_search"
    assert result["fallback_used"] is True
    assert result["cp_sat_failure_reason"] == "solver_unknown"
    assert provider.calls == 1
    assert result["output"].evaluation is not None
    assert any("Beam Search was used as fallback" in item for item in result["warnings"])


def test_cp_sat_route_failure_also_falls_back_to_beam(monkeypatch) -> None:
    provider = GeneratedMatrixProvider()
    original_factory = graph_module.create_enrich_selected_routes_node

    def enrichment_factory(*args, beam_mode=False, **kwargs):
        if beam_mode:
            return original_factory(*args, beam_mode=True, **kwargs)

        async def fail_cp_sat_enrichment(_state):
            return {
                "error": "CP-SAT route detail is invalid.",
                "error_code": "route_detail_timeline_invalid",
            }

        return fail_cp_sat_enrichment

    monkeypatch.setattr(
        graph_module,
        "create_enrich_selected_routes_node",
        enrichment_factory,
    )
    graph = build_cp_sat_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )

    result = asyncio.run(graph.ainvoke({"input": _planner_input()}))

    assert result.get("error") is None
    assert result["selected_optimizer"] == "beam_search"
    assert result["cp_sat_failure_reason"] == "route_detail_timeline_invalid"
    assert result["fallback_used"] is True
    assert provider.calls == 1


def test_cp_sat_first_graph_does_not_fallback_for_shared_preflight_error() -> None:
    provider = GeneratedMatrixProvider()
    graph = build_cp_sat_first_itinerary_planner_graph(
        provider,
        FixedCostEstimator(),
    )
    raw = payload()
    raw["food"][0]["supportedMeals"] = ["lunch", "dinner"]

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert result["error_code"] == "missing_meal_coverage"
    assert "selected_optimizer" not in result
    assert provider.calls == 0
