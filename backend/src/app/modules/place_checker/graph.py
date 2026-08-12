from langgraph.graph import END, START, StateGraph

from app.modules.place_checker.adapters import DevelopmentCatalog
from app.modules.place_checker.nodes import create_check_node, create_pipeline_node
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.service import PlaceCheckerService
from app.modules.place_checker.state import PlaceCheckerPipelineState, PlaceCheckerState


def build_place_checker_graph(service: PlaceCheckerService | None = None):
    if service is None:
        catalog = DevelopmentCatalog()
        service = PlaceCheckerService(catalog, catalog)
    builder = StateGraph(PlaceCheckerState)
    builder.add_node("check_places", create_check_node(service))
    builder.add_edge(START, "check_places")
    builder.add_edge("check_places", END)
    return builder.compile()


def build_place_checker_pipeline_graph(pipeline: PlaceCheckerPipeline):
    builder = StateGraph(PlaceCheckerPipelineState)
    builder.add_node("place_checker_pipeline", create_pipeline_node(pipeline))
    builder.add_edge(START, "place_checker_pipeline")
    builder.add_edge("place_checker_pipeline", END)
    return builder.compile()
