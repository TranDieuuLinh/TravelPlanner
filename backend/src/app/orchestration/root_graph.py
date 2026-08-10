from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes import RootNodes
from app.orchestration.root_state import RootState
from app.orchestration.routes import route_after_explorer, route_supervisor
from app.shared.persistence import create_checkpointer


def create_root_graph(
    *, checkpointer=None, information_finder_service=None, supervisor_service=None
):
    nodes = RootNodes(information_finder_service, supervisor_service)
    builder = StateGraph(RootState)

    builder.add_node("supervisor", nodes.run_supervisor)
    builder.add_node("explorer", nodes.run_explorer)
    builder.add_node("information_finder", nodes.run_information_finder)
    builder.add_node("place_checker", nodes.run_place_checker)
    builder.add_node("itinerary_planner", nodes.run_itinerary_planner)
    builder.add_node("plan_editor", nodes.run_plan_editor)
    builder.add_node("finish", nodes.finish)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "explorer": "explorer",
            "information_finder": "information_finder",
            "plan_editor": "plan_editor",
            "finish": "finish",
        },
    )
    builder.add_conditional_edges(
        "explorer",
        route_after_explorer,
        {"place_checker": "place_checker", "finish": "finish"},
    )
    builder.add_edge("place_checker", "itinerary_planner")
    builder.add_edge("itinerary_planner", "finish")
    builder.add_edge("information_finder", "finish")
    builder.add_edge("plan_editor", "finish")
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer or create_checkpointer())


graph = create_root_graph()

