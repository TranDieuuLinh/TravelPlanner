from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.service import ExplorerService
from app.modules.explorer.state import ExplorerState


def create_explore_node(service: ExplorerService):
    def explore(state: ExplorerState) -> dict:
        output = service.explore(
            ExplorerInput(
                message=state["message"],
                supplied_candidates=state.get("supplied_candidates", []),
            )
        )
        return {"output": output}

    return explore

