import asyncio

from app.modules.explorer.public import build_explorer_graph
from app.modules.place_checker.tests.test_pipeline_output import pipeline
from app.orchestration.nodes import RootNodes


def test_prompt_preferences_reach_place_checker_before_pool_gate() -> None:
    explorer = asyncio.run(
        build_explorer_graph().ainvoke(
            {"payload": {"rawPrompt": ("Đi Hà Nội 1 ngày, thích văn hóa. Muốn ăn phở")}}
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

    output = update["place_output"]
    pho = next(item for item in output.resolved_items if item.selected)
    assert output.trip_context.preferences == [
        "văn hóa",
        "giá rẻ",
        "địa phương",
        "ẩm thực",
        "thiên nhiên",
        "biển",
        "núi",
        "cảnh quan",
    ]
    assert output.trip_context.avoids == ["sang trọng"]
    assert pho.selected.place_id == "kg:pho"
    assert output.status.value == "blocked"
    assert "planner_input" not in update
