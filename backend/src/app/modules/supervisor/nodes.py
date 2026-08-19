from app.modules.supervisor.contract import SupervisorInput
from app.modules.supervisor.service import SupervisorService
from app.modules.supervisor.state import SupervisorState


def create_decide_node(service: SupervisorService):
    async def decide(state: SupervisorState) -> dict:
        decision = await service.decide(
            SupervisorInput(
                message=state["message"],
                conversation_context=state.get("conversation_context", []),
                has_source_input=state.get("has_source_input", False),
                has_itinerary=state.get("has_itinerary", False),
                has_edit_operation=state.get("has_edit_operation", False),
                destination=state.get("destination"),
                duration_days=state.get("duration_days"),
                mentioned_places=state.get("mentioned_places", []),
                selected_places=state.get("selected_places", []),
                clarification_required=state.get("clarification_required", False),
                conversation_summary=state.get("conversation_summary"),
            )
        )
        return {"decision": decision}

    return decide
