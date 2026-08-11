from langgraph.graph import END, START, StateGraph

from app.modules.plan_editor.nodes import create_edit_node
from app.modules.plan_editor.service import PlanEditorService
from app.modules.plan_editor.state import PlanEditorState


def build_plan_editor_graph(service: PlanEditorService | None = None):
    builder = StateGraph(PlanEditorState)
    builder.add_node("edit", create_edit_node(service or PlanEditorService()))
    builder.add_edge(START, "edit")
    builder.add_edge("edit", END)
    return builder.compile()
