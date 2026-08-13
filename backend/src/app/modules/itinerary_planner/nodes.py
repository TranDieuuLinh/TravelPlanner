from app.modules.itinerary_planner.legacy_contract import LegacyItineraryPlannerInput
from app.modules.itinerary_planner.service import ItineraryPlannerService
from app.modules.itinerary_planner.state import ItineraryPlannerState


def create_plan_node(service: ItineraryPlannerService):
    async def plan(state: ItineraryPlannerState) -> dict:
        output = await service.plan(
            LegacyItineraryPlannerInput(
                intent=state["intent"],
                places=state.get("places", []),
                upstream_warnings=state.get("upstream_warnings", []),
            )
        )
        return {"output": output}

    return plan
