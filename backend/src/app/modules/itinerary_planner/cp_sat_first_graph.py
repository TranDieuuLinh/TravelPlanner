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


def build_cp_sat_first_itinerary_planner_graph(
    matrix_provider: RoutingMatrixProvider | None = None,
    transport_cost_estimator: TransportCostEstimator | None = None,
    matrix_cache: MatrixCache | None = None,
    route_detail_provider: RouteDetailProvider | None = None,
    *,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
    provider_namespace: str = "valhalla:unknown",
    solver_config: SolverConfig | None = None,
    objective_weights: ObjectiveWeights | None = None,
    beam_config: BeamSearchConfig | None = None,
):
    """Run Hybrid CP-SAT first and use Beam Search only as fallback."""
    selected_solver_config = solver_config or SolverConfig()
    selected_weights = objective_weights or ObjectiveWeights()
    optimize_cp_sat = create_optimize_itinerary_node(
        selected_solver_config,
        selected_weights,
    )
    optimize_beam = create_optimize_beam_search_node(beam_config)
    enrich_cp_sat = create_enrich_selected_routes_node(
        route_detail_provider,
        transport_cost_estimator,
        selected_solver_config,
        selected_weights,
    )
    enrich_beam = create_enrich_selected_routes_node(
        route_detail_provider,
        transport_cost_estimator,
        SolverConfig(max_inter_stop_wait_minutes=60),
        selected_weights,
        beam_mode=True,
    )

    async def try_cp_sat(state: ItineraryPlannerState) -> dict:
        result = await optimize_cp_sat(state)
        if result.get("error"):
            return _cp_sat_failure(result, "cp_sat_error")
        optimization = result.get("optimization_result")
        if optimization is None:
            return _cp_sat_failure({}, "cp_sat_output_missing")
        if optimization.status not in {"OPTIMAL", "FEASIBLE"}:
            return _cp_sat_failure(
                {},
                f"cp_sat_status_{optimization.status.casefold()}",
            )
        return {**result, "selected_optimizer": "hybrid_cp_sat"}

    async def try_enrich_cp_sat(state: ItineraryPlannerState) -> dict:
        result = await enrich_cp_sat(state)
        if result.get("error"):
            return _cp_sat_failure(result, "cp_sat_route_error")
        return result

    async def run_beam_fallback(state: ItineraryPlannerState) -> dict:
        result = await optimize_beam(state)
        if result.get("error"):
            return result
        optimization = result.get("optimization_result")
        if optimization is None:
            return {
                "error": "Beam Search fallback returned no optimization result.",
                "error_code": "beam_output_missing",
            }
        if optimization.status != "FEASIBLE":
            return {
                "error": f"Beam Search fallback returned {optimization.status}.",
                "error_code": f"beam_status_{optimization.status.casefold()}",
            }
        reason = state.get("cp_sat_failure_reason", "cp_sat_error")
        warning = _fallback_warning(reason)
        return {
            **result,
            "warnings": list(
                dict.fromkeys([*state.get("warnings", []), warning])
            ),
            "selected_optimizer": "beam_search",
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
    builder.add_node("optimize_cp_sat", try_cp_sat)
    builder.add_node("enrich_cp_sat", try_enrich_cp_sat)
    builder.add_node("optimize_beam", run_beam_fallback)
    builder.add_node("enrich_beam", enrich_beam)
    builder.add_node("finalize_output", finalize_output_node)
    builder.add_edge(START, "prepare_problem")
    builder.add_edge("prepare_problem", "build_travel_matrix")
    builder.add_conditional_edges(
        "build_travel_matrix",
        _route_after_shared_prefix,
        {"cp_sat": "optimize_cp_sat", "stop": END},
    )
    builder.add_conditional_edges(
        "optimize_cp_sat",
        _route_after_cp_sat,
        {"enrich": "enrich_cp_sat", "beam": "optimize_beam"},
    )
    builder.add_conditional_edges(
        "enrich_cp_sat",
        _route_after_cp_sat_enrichment,
        {"finalize": "finalize_output", "beam": "optimize_beam"},
    )
    builder.add_conditional_edges(
        "optimize_beam",
        _route_after_beam,
        {"enrich": "enrich_beam", "stop": END},
    )
    builder.add_conditional_edges(
        "enrich_beam",
        _route_after_beam_enrichment,
        {"finalize": "finalize_output", "stop": END},
    )
    builder.add_edge("finalize_output", END)
    return builder.compile(checkpointer=False)


def _cp_sat_failure(result: dict, default_reason: str) -> dict:
    reason = str(result.get("error_code") or default_reason)
    message = str(result.get("error") or "Hybrid CP-SAT returned no feasible result.")
    return {
        "cp_sat_failure_reason": reason,
        "cp_sat_failure_message": message,
    }


def _route_after_shared_prefix(
    state: ItineraryPlannerState,
) -> Literal["cp_sat", "stop"]:
    return "stop" if state.get("error") else "cp_sat"


def _route_after_cp_sat(
    state: ItineraryPlannerState,
) -> Literal["enrich", "beam"]:
    return "beam" if state.get("cp_sat_failure_reason") else "enrich"


def _route_after_cp_sat_enrichment(
    state: ItineraryPlannerState,
) -> Literal["finalize", "beam"]:
    return "beam" if state.get("cp_sat_failure_reason") else "finalize"


def _route_after_beam(
    state: ItineraryPlannerState,
) -> Literal["enrich", "stop"]:
    return "stop" if state.get("error") else "enrich"


def _route_after_beam_enrichment(
    state: ItineraryPlannerState,
) -> Literal["finalize", "stop"]:
    return "stop" if state.get("error") else "finalize"


def _fallback_warning(reason: str) -> str:
    return (
        "Hybrid CP-SAT was not used successfully ("
        f"{reason}); Beam Search was used as fallback."
    )
