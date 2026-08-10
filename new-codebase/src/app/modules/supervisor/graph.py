from langgraph.graph import END, START, StateGraph

from app.modules.supervisor.nodes import create_decide_node
from app.modules.supervisor.service import SupervisorService
from app.modules.supervisor.state import SupervisorState


def build_supervisor_graph(service: SupervisorService | None = None):
    builder = StateGraph(SupervisorState)
    builder.add_node("decide", create_decide_node(service or SupervisorService()))
    builder.add_edge(START, "decide")
    builder.add_edge("decide", END)
    return builder.compile()

