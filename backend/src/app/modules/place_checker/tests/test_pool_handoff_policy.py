import asyncio

from app.modules.place_checker.planning.builder import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.enums import PlaceCheckerStatus
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.selection.food.contract import FoodMealCoverage
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline


def test_pipeline_does_not_block_on_travel_reserve_shortfall() -> None:
    base = asyncio.run(pipeline().check(payload(), request_id="request-travel-reserve"))
    ready = base.model_copy(
        update={
            "status": PlaceCheckerStatus.conditional,
            "food_meal_coverage": FoodMealCoverage(days=1, hardComplete=True),
        }
    )
    result = PlaceCheckerPipeline._apply_food_pool_policy(
        ready,
        pool_warnings=["Planner travel reserve is partial: missing 100."],
        food_target=6,
        missing_food=0,
    )

    assert result.status.value != "blocked"
    assert any("Planner travel reserve is partial" in item for item in result.warnings)


def test_pipeline_does_not_block_on_food_reserve_when_hard_meals_are_complete() -> None:
    base = asyncio.run(pipeline().check(payload(), request_id="request-food-reserve"))
    ready = base.model_copy(
        update={
            "status": PlaceCheckerStatus.conditional,
            "food_meal_coverage": FoodMealCoverage(
                days=1,
                hardComplete=True,
                reserveComplete=False,
            ),
        }
    )

    result = PlaceCheckerPipeline._apply_food_pool_policy(
        ready,
        pool_warnings=[],
        food_target=6,
        missing_food=2,
    )

    assert result.status == PlaceCheckerStatus.conditional
    assert any("Planner meal reserve is partial" in item for item in result.warnings)


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
