from app.modules.itinerary_planner.contract import (
    ItineraryPlannerInput,
)
from app.modules.itinerary_planner.output_contract import ItineraryPlannerOutput
from app.modules.itinerary_planner.adapters import (
    FallbackRoutingAdapter,
    InMemoryMatrixCache,
    StraightLineRoutingAdapter,
    ValhallaAdapter,
)
from app.modules.itinerary_planner.graph import build_itinerary_planner_graph
from app.shared.tools.transport_cost import XanhSmTransportCostEstimator


def build_valhalla_itinerary_planner_graph(
    base_url: str,
    *,
    timeout_seconds: float = 15,
    provider_version: str = "local",
):
    valhalla = ValhallaAdapter(
        base_url,
        timeout_seconds=timeout_seconds,
        provider_version=provider_version,
    )
    adapter = FallbackRoutingAdapter(valhalla, StraightLineRoutingAdapter())
    return build_itinerary_planner_graph(
        adapter,
        XanhSmTransportCostEstimator(),
        InMemoryMatrixCache(),
        adapter,
        provider_namespace=f"valhalla:{provider_version}",
    )

__all__ = [
    "ItineraryPlannerInput",
    "ItineraryPlannerOutput",
    "build_itinerary_planner_graph",
    "build_valhalla_itinerary_planner_graph",
]
