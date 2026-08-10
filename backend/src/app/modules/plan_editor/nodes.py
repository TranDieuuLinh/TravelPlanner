from app.modules.plan_editor.contract import PlanEditorInput
from app.modules.plan_editor.service import PlanEditorService
from app.modules.plan_editor.state import PlanEditorState


def create_edit_node(service: PlanEditorService):
    def edit(state: PlanEditorState) -> dict:
        output = service.edit(
            PlanEditorInput(
                itinerary=state["itinerary"],
                operation=state["operation"],
            )
        )
        return {"output": output}

    return edit

