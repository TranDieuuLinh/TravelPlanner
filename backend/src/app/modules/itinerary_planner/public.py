from app.modules.itinerary_planner.contract import (
    FoodCoverageFeasibility,
    ItineraryPlannerInput,
    MealSlotAssignment,
    MissingMealSlot,
    PlannerPreflightFailure,
)
from app.modules.itinerary_planner.output_contract import ItineraryPlannerOutput
from app.modules.itinerary_planner.adapters import (
    FallbackRoutingAdapter,
    InMemoryMatrixCache,
    StraightLineRoutingAdapter,
    ValhallaAdapter,
)
from app.modules.itinerary_planner.directions import DirectionsService, router
from app.modules.itinerary_planner.graph import build_itinerary_planner_graph
from app.modules.itinerary_planner.beam_search.graph import (
    build_beam_search_itinerary_planner_graph,
)
from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.fallback import BeamFirstFallbackPlanner
from app.modules.itinerary_planner.optimizer import SolverConfig
from app.shared.tools.transport_cost import XanhSmTransportCostEstimator


def build_valhalla_itinerary_planner_graph(
    base_url: str,
    *,
    timeout_seconds: float | None = None,
    provider_version: str = "local",
    log_search_progress: bool = False,
):
    valhalla = ValhallaAdapter(base_url, timeout_seconds=timeout_seconds, provider_version=provider_version)
    adapter = FallbackRoutingAdapter(valhalla, StraightLineRoutingAdapter())
    return build_itinerary_planner_graph(
        adapter,
        XanhSmTransportCostEstimator(),
        InMemoryMatrixCache(),
        adapter,
        provider_namespace=f"valhalla:{provider_version}",
        solver_config=SolverConfig(log_search_progress=log_search_progress),
    )


def build_valhalla_beam_search_itinerary_planner_graph(
    base_url: str,
    *,
    timeout_seconds: float | None = None,
    provider_version: str = "local",
    beam_config: BeamSearchConfig | None = None,
):
    valhalla = ValhallaAdapter(
        base_url, timeout_seconds=timeout_seconds, provider_version=provider_version
    )
    adapter = FallbackRoutingAdapter(valhalla, StraightLineRoutingAdapter())
    return build_beam_search_itinerary_planner_graph(
        adapter,
        XanhSmTransportCostEstimator(),
        InMemoryMatrixCache(),
        adapter,
        provider_namespace=f"valhalla:{provider_version}",
        beam_config=beam_config,
    )


def build_valhalla_beam_first_itinerary_planner_graph(
    base_url: str,
    *,
    timeout_seconds: float | None = None,
    provider_version: str = "local",
    beam_config: BeamSearchConfig | None = None,
    log_search_progress: bool = False,
):
    valhalla = ValhallaAdapter(
        base_url, timeout_seconds=timeout_seconds, provider_version=provider_version
    )
    adapter = FallbackRoutingAdapter(valhalla, StraightLineRoutingAdapter())
    matrix_cache = InMemoryMatrixCache()
    hybrid_graph = build_itinerary_planner_graph(
        adapter,
        XanhSmTransportCostEstimator(),
        matrix_cache,
        adapter,
        provider_namespace=f"valhalla:{provider_version}",
        solver_config=SolverConfig(log_search_progress=log_search_progress),
    )
    beam_graph = build_beam_search_itinerary_planner_graph(
        adapter,
        XanhSmTransportCostEstimator(),
        matrix_cache,
        adapter,
        provider_namespace=f"valhalla:{provider_version}",
        beam_config=beam_config,
    )
    return BeamFirstFallbackPlanner(beam_graph, hybrid_graph)


def build_valhalla_directions_service(
    base_url: str,
    *,
    timeout_seconds: float = 15,
    provider_version: str = "local",
) -> DirectionsService:
    valhalla = ValhallaAdapter(
        base_url,
        timeout_seconds=timeout_seconds,
        provider_version=provider_version,
    )
    return DirectionsService(FallbackRoutingAdapter(valhalla, StraightLineRoutingAdapter()))

__all__ = [
    "ItineraryPlannerInput",
    "FoodCoverageFeasibility",
    "MealSlotAssignment",
    "MissingMealSlot",
    "PlannerPreflightFailure",
    "ItineraryPlannerOutput",
    "build_itinerary_planner_graph",
    "build_valhalla_itinerary_planner_graph",
    "build_beam_search_itinerary_planner_graph",
    "build_valhalla_beam_search_itinerary_planner_graph",
    "build_valhalla_beam_first_itinerary_planner_graph",
    "build_valhalla_directions_service",
    "router",
]
