import asyncio
from unittest.mock import patch

from app.modules.place_checker.planning_output import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline


def test_pipeline_does_not_block_on_travel_reserve_shortfall() -> None:
    with patch.object(
        PlaceCheckerPlannerOutputBuilder,
        "pool_shortfall",
        return_value=(24, 9, 100, 0),
    ):
        result = asyncio.run(
            pipeline().check(payload(), request_id="request-travel-reserve")
        )

    assert result.status.value != "blocked"
    assert any("Planner travel reserve is partial" in item for item in result.warnings)


def test_food_pool_cap_never_drops_required_inputs_above_reserve_limit() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-food-required-cap"))
    projected = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    ).food[0]
    required = [
        projected.model_copy(update={"place_id": f"required:{index}"})
        for index in range(4)
    ]

    limited = PlaceCheckerPlannerOutputBuilder._limit_food_pool(
        required,
        limit=2,
        required_ids={item.place_id for item in required},
        paired_ids=set(),
    )

    assert [item.place_id for item in limited] == [
        "required:0",
        "required:1",
        "required:2",
        "required:3",
    ]


def test_place_pool_cap_never_drops_url_or_user_inputs_above_reserve_limit() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-place-priority-cap"))
    sample = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    ).places[0]
    candidates = [
        sample.model_copy(update={"place_id": f"input:{index}", "priority": "url"})
        for index in range(4)
    ]

    limited = PlaceCheckerPlannerOutputBuilder._limit_optional_pool(candidates, limit=2)

    assert [item.place_id for item in limited] == [
        "input:0",
        "input:1",
        "input:2",
        "input:3",
    ]
