from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.nodes import (
    create_optimize_beam_search_node,
)
from app.modules.itinerary_planner.nodes import (
    create_build_travel_matrix_node,
    create_enrich_selected_routes_node,
    create_optimize_itinerary_node,
    finalize_output_node,
    prepare_problem_node,
)
from app.modules.itinerary_planner.optimizer import ObjectiveWeights, SolverConfig
from app.modules.itinerary_planner.ports import (
    MatrixCache,
    RouteDetailProvider,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.routing import DEFAULT_NEIGHBOR_LIMIT
from app.modules.itinerary_planner.state import ItineraryPlannerState
from app.shared.tools.transport_cost import TransportCostEstimator


def build_beam_first_itinerary_planner_graph(
    matrix_provider: RoutingMatrixProvider | None = None,
    transport_cost_estimator: TransportCostEstimator | None = None,
    matrix_cache: MatrixCache | None = None,
    route_detail_provider: RouteDetailProvider | None = None,
    *,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
    provider_namespace: str = "valhalla:unknown",
    beam_config: BeamSearchConfig | None = None,
    solver_config: SolverConfig | None = None,
    objective_weights: ObjectiveWeights | None = None,
):
    selected_solver_config = solver_config or SolverConfig()
    selected_weights = objective_weights or ObjectiveWeights()
    optimize_beam = create_optimize_beam_search_node(beam_config)
    optimize_hybrid = create_optimize_itinerary_node(
        selected_solver_config, selected_weights
    )
    enrich_beam = create_enrich_selected_routes_node(
        route_detail_provider,
        transport_cost_estimator,
        SolverConfig(max_inter_stop_wait_minutes=60),
        selected_weights,
        beam_mode=True,
    )
    enrich_hybrid = create_enrich_selected_routes_node(
        route_detail_provider,
        transport_cost_estimator,
        selected_solver_config,
        selected_weights,
    )

    async def try_beam(state: ItineraryPlannerState) -> dict:
        result = await optimize_beam(state)
        if result.get("error"):
            return {
                "beam_failure_reason": str(
                    result.get("error_code") or "beam_search_error"
                ),
                "beam_failure_message": str(result["error"]),
            }
        optimization = result.get("optimization_result")
        if optimization is None:
            return {
                "beam_failure_reason": "beam_output_missing",
                "beam_failure_message": "Beam Search returned no optimization result.",
            }
        if optimization.status != "FEASIBLE":
            return {
                **result,
                "beam_failure_reason": f"beam_status_{optimization.status.casefold()}",
                "beam_failure_message": (
                    f"Beam Search returned {optimization.status}."
                ),
            }
        return {**result, "selected_optimizer": "beam_search"}

    async def try_enrich_beam(state: ItineraryPlannerState) -> dict:
        result = await enrich_beam(state)
        if result.get("error"):
            return {
                "beam_failure_reason": str(
                    result.get("error_code") or "beam_route_error"
                ),
                "beam_failure_message": str(result["error"]),
            }
        return result

    async def run_hybrid(state: ItineraryPlannerState) -> dict:
        result = await optimize_hybrid(state)
        if result.get("error"):
            return result
        reason = state.get("beam_failure_reason", "beam_search_error")
        warning = _fallback_warning(reason)
        return {
            **result,
            "warnings": [*state.get("warnings", []), warning],
            "selected_optimizer": "hybrid_cp_sat",
            "fallback_used": True,
        }

    builder = StateGraph(ItineraryPlannerState)
    builder.add_node("prepare_problem", prepare_problem_node)
    builder.add_node(
        "build_travel_matrix",
        create_build_travel_matrix_node(
            matrix_provider,
            transport_cost_estimator,
            matrix_cache,
            neighbor_limit=neighbor_limit,
            provider_namespace=provider_namespace,
        ),
    )
    builder.add_node("optimize_beam", try_beam)
    builder.add_node("enrich_beam", try_enrich_beam)
    builder.add_node("optimize_hybrid", run_hybrid)
    builder.add_node("enrich_hybrid", enrich_hybrid)
    builder.add_node("finalize_output", finalize_output_node)
    builder.add_edge(START, "prepare_problem")
    builder.add_edge("prepare_problem", "build_travel_matrix")
    builder.add_conditional_edges(
        "build_travel_matrix",
        _route_after_shared_prefix,
        {"beam": "optimize_beam", "stop": END},
    )
    builder.add_conditional_edges(
        "optimize_beam",
        _route_after_beam,
        {"enrich": "enrich_beam", "hybrid": "optimize_hybrid"},
    )
    builder.add_conditional_edges(
        "enrich_beam",
        _route_after_beam_enrichment,
        {"finalize": "finalize_output", "hybrid": "optimize_hybrid"},
    )
    builder.add_conditional_edges(
        "optimize_hybrid",
        _route_after_hybrid,
        {"enrich": "enrich_hybrid", "stop": END},
    )
    builder.add_conditional_edges(
        "enrich_hybrid",
        _route_after_hybrid_enrichment,
        {"finalize": "finalize_output", "stop": END},
    )
    builder.add_edge("finalize_output", END)
    return builder.compile(checkpointer=False)


def _route_after_shared_prefix(
    state: ItineraryPlannerState,
) -> Literal["beam", "stop"]:
    return "stop" if state.get("error") else "beam"


def _route_after_beam(
    state: ItineraryPlannerState,
) -> Literal["enrich", "hybrid"]:
    return "hybrid" if state.get("beam_failure_reason") else "enrich"


def _route_after_beam_enrichment(
    state: ItineraryPlannerState,
) -> Literal["finalize", "hybrid"]:
    return "hybrid" if state.get("beam_failure_reason") else "finalize"


def _route_after_hybrid(
    state: ItineraryPlannerState,
) -> Literal["enrich", "stop"]:
    return "stop" if state.get("error") else "enrich"


def _route_after_hybrid_enrichment(
    state: ItineraryPlannerState,
) -> Literal["finalize", "stop"]:
    return "stop" if state.get("error") else "finalize"


def _fallback_warning(reason: str) -> str:
    return (
        "Beam Search was not used successfully ("
        f"{reason}); Hybrid planner was used as fallback."
    )
