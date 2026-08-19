from langgraph.graph import END, START, StateGraph

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.nodes import create_optimize_beam_search_node
from app.modules.itinerary_planner.nodes import (
    create_build_travel_matrix_node,
    create_enrich_selected_routes_node,
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


def build_beam_search_itinerary_planner_graph(
    matrix_provider: RoutingMatrixProvider | None = None,
    transport_cost_estimator: TransportCostEstimator | None = None,
    matrix_cache: MatrixCache | None = None,
    route_detail_provider: RouteDetailProvider | None = None,
    *,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
    provider_namespace: str = "valhalla:unknown",
    beam_config: BeamSearchConfig | None = None,
):
    """Build the parallel Beam Search graph; the existing CP-SAT graph is untouched."""
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
    builder.add_node(
        "optimize_itinerary", create_optimize_beam_search_node(beam_config)
    )
    builder.add_node(
        "enrich_selected_routes",
        create_enrich_selected_routes_node(
            route_detail_provider,
            transport_cost_estimator,
            SolverConfig(max_inter_stop_wait_minutes=60),
            ObjectiveWeights(),
            beam_mode=True,
        ),
    )
    builder.add_node("finalize_output", finalize_output_node)
    builder.add_edge(START, "prepare_problem")
    builder.add_edge("prepare_problem", "build_travel_matrix")
    builder.add_edge("build_travel_matrix", "optimize_itinerary")
    builder.add_edge("optimize_itinerary", "enrich_selected_routes")
    builder.add_edge("enrich_selected_routes", "finalize_output")
    builder.add_edge("finalize_output", END)
    return builder.compile(checkpointer=False)
