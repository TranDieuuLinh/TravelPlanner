from app.modules.information_finder.service import InformationFinderService
from app.modules.information_finder.state import InformationFinderState


def create_find_node(service: InformationFinderService):
    async def find(state: InformationFinderState) -> dict:
        return {"output": await service.find(
            state["query"], force_refresh=state.get("force_refresh", False)
        )}

    return find
