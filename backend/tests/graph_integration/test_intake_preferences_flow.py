import asyncio

from app.modules.explorer.public import build_explorer_graph
from app.modules.place_checker.tests.test_pipeline_output import pipeline
from app.orchestration.nodes import RootNodes


def test_prompt_preferences_and_input_item_reach_planner_contract() -> None:
    explorer = asyncio.run(
        build_explorer_graph().ainvoke(
            {
                "payload": {
                    "rawPrompt": (
                        "Đi Hà Nội 1 ngày, thích văn hóa. Muốn ăn phở"
                    )
                }
            }
        )
    )["output"]
    nodes = RootNodes(place_checker_pipeline=pipeline())

    update = asyncio.run(
        nodes.run_place_checker(
            {
                "request_id": "intake-preferences-flow",
                "explorer_output": explorer,
                "warnings": [],
            }
        )
    )

    planner_input = update["planner_input"]
    pho = next(item for item in planner_input.food if item.place_id == "kg:pho")
    assert planner_input.trip.preferences == ["culture"]
    assert pho.priority.value == "user_input"
