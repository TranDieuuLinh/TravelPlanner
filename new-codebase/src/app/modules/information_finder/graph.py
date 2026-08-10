from langgraph.graph import END, START, StateGraph

from app.modules.information_finder.nodes import create_find_node
from app.modules.information_finder.ports import UnconfiguredInformationProvider
from app.modules.information_finder.service import InformationFinderService
from app.modules.information_finder.state import InformationFinderState


def build_information_finder_graph(
    service: InformationFinderService | None = None,
):
    selected_service = service or InformationFinderService(
        UnconfiguredInformationProvider()
    )
    builder = StateGraph(InformationFinderState)
    builder.add_node("find", create_find_node(selected_service))
    builder.add_edge(START, "find")
    builder.add_edge("find", END)
    return builder.compile()

