from app.modules.place_checker.contract import PlaceCheckerInput
from app.modules.place_checker.service import PlaceCheckerService
from app.modules.place_checker.state import PlaceCheckerState


def create_check_node(service: PlaceCheckerService):
    async def check(state: PlaceCheckerState) -> dict:
        output = await service.check(
            PlaceCheckerInput(
                intent=state["intent"],
                candidates=state.get("candidates", []),
            )
        )
        return {"output": output}

    return check

