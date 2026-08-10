from langgraph.graph import END, START, StateGraph

from app.modules.explorer.nodes import create_explore_node
from app.modules.explorer.service import ExplorerService
from app.modules.explorer.state import ExplorerState


def build_explorer_graph(service: ExplorerService | None = None):
    builder = StateGraph(ExplorerState)
    builder.add_node("explore", create_explore_node(service or ExplorerService()))
    builder.add_edge(START, "explore")
    builder.add_edge("explore", END)
    return builder.compile()

