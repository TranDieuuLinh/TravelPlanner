from app.modules.explorer.public import ExplorerBudget, ExplorerPeople
from app.modules.place_checker.contract import PlaceCheckerInput
from app.modules.place_checker.service import PlaceCheckerService
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.state import (
    PlaceCheckerPipelineState,
    PlaceCheckerState,
)


def create_check_node(service: PlaceCheckerService):
    async def check(state: PlaceCheckerState) -> dict:
        output = await service.check(
            PlaceCheckerInput(
                input_ADM=state["input_adm"],
                places=state.get("places"),
                input_items=state.get("input_items"),
                url_notes=state.get("url_notes"),
                days=state.get("days", 3),
                budget=state.get("budget") or ExplorerBudget(),
                people=state.get("people") or ExplorerPeople(),
                short_preferences=state.get("short_preferences", []),
                short_avoids=state.get("short_avoids", []),
                special_notes=state.get("special_notes", []),
            )
        )
        return {"output": output}

    return check


def create_pipeline_node(pipeline: PlaceCheckerPipeline):
    async def check(state: PlaceCheckerPipelineState) -> dict:
        payload = PlaceCheckerInput.model_validate(state["payload"])
        result = await pipeline.check(
            payload,
            request_id=state["request_id"],
            correlation_id=state.get("correlation_id"),
        )
        return {"result": result}

    return check
