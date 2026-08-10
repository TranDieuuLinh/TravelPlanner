from langgraph.graph import END, START, StateGraph

from app.modules.place_checker.adapters import DevelopmentCatalog
from app.modules.place_checker.nodes import create_check_node
from app.modules.place_checker.service import PlaceCheckerService
from app.modules.place_checker.state import PlaceCheckerState


def build_place_checker_graph(service: PlaceCheckerService | None = None):
    if service is None:
        catalog = DevelopmentCatalog()
        service = PlaceCheckerService(catalog, catalog)
    builder = StateGraph(PlaceCheckerState)
    builder.add_node("check_places", create_check_node(service))
    builder.add_edge(START, "check_places")
    builder.add_edge("check_places", END)
    return builder.compile()

