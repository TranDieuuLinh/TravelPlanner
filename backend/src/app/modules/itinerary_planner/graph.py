from langgraph.graph import END, START, StateGraph

from app.modules.itinerary_planner.nodes import create_plan_node
from app.modules.itinerary_planner.ports import EstimatedRoutingProvider
from app.modules.itinerary_planner.service import ItineraryPlannerService
from app.modules.itinerary_planner.state import ItineraryPlannerState


def build_itinerary_planner_graph(
    service: ItineraryPlannerService | None = None,
):
    selected_service = service or ItineraryPlannerService(EstimatedRoutingProvider())
    builder = StateGraph(ItineraryPlannerState)
    builder.add_node("build_itinerary", create_plan_node(selected_service))
    builder.add_edge(START, "build_itinerary")
    builder.add_edge("build_itinerary", END)
    return builder.compile()

