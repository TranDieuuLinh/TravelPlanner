from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes import RootNodes
from app.orchestration.root_state import RootState
from app.orchestration.routes import (
    route_after_explorer,
    route_after_place_checker,
    route_supervisor,
)
from app.shared.persistence import create_checkpointer


def create_root_graph(
    *, checkpointer=None, information_finder_service=None, supervisor_service=None,
    explorer_service=None, place_checker_pipeline=None, itinerary_planner_graph=None,
    database_url: str | None = None,
):
    nodes = RootNodes(
        information_finder_service,
        supervisor_service,
        explorer_service,
        place_checker_pipeline,
        itinerary_planner_graph,
    )
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
        {"place_checker": "place_checker", "information_finder": "information_finder", "finish": "finish"},
    )
    builder.add_conditional_edges(
        "place_checker",
        route_after_place_checker,
        {"itinerary_planner": "itinerary_planner", "finish": "finish"},
    )
    builder.add_edge("itinerary_planner", "finish")
    builder.add_edge("information_finder", "finish")
    builder.add_edge("plan_editor", "finish")
    builder.add_edge("finish", END)

    compile_checkpointer = (
        create_checkpointer(database_url)
        if checkpointer is None
        else (None if checkpointer is False else checkpointer)
    )
    return builder.compile(checkpointer=compile_checkpointer)


# LangGraph Studio imports this symbol and manages its own run persistence.
# The FastAPI runtime uses bootstrap.get_graph(), which injects the configured
# durable PostgreSQL checkpointer. Avoid constructing a misleading RAM saver at
# module import time.
graph = create_root_graph(checkpointer=False)
