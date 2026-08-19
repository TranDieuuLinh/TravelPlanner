import asyncio

from app.modules.place_checker.enums import CostTier
from app.modules.place_checker.food_selection_contract import SelectedFoodRestaurant
from app.modules.place_checker.planning_output import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.tests.test_pipeline_output import (
    metadata,
    payload,
    pipeline,
)


def test_existing_food_pool_candidate_counts_as_special_near_by_relationship() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="existing-food-pair"))
    anchor = result.checked_places[0]
    selection = SelectedFoodRestaurant(
        anchor_place_id=anchor.place_id,
        anchor_name=anchor.canonical_name,
        food_item_id="food:pho",
        food_item_name="Phở",
        offered_food_item_id="food:pho",
        offered_food_item_name="Phở",
        food_match_type="direct_id",
        food_match_confidence=1,
        restaurant_id="kg:pho",
        restaurant_name="Pho Hanoi",
        distance_km=0.5,
        rating=4.5,
        review_count=1_000,
        bayesian_rating=4.5,
        pair_score=0.9,
        selection_reason="sole_candidate_for_food",
        metadata=metadata(
            "kg:pho",
            category="restaurant",
            cost_tier=CostTier.low,
            latitude=21.0338,
        ),
    )
    result = result.model_copy(update={"food_restaurant_selections": [selection]})
    builder = PlaceCheckerPlannerOutputBuilder()

    output = builder.build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )
    existing = next(food for food in output.food if food.place_id == "kg:pho")

    assert existing.priority == "user_input"
    assert anchor.place_id in existing.relationships
    assert anchor.place_id not in builder.unpaired_travel_place_ids(result)


def test_general_food_without_meal_window_does_not_fill_planner_pool() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="invalid-general-food"))
    sample = result.checked_places[0]
    invalid_food = sample.model_copy(
        update={
            "place_id": "restaurant:no-meal-window",
            "canonical_name": "No Meal Window",
            "category": "restaurant",
            "mandatory": False,
            "opening": sample.opening.model_copy(update={"hours": []}),
        }
    )
    result = result.model_copy(
        update={"checked_places": [*result.checked_places, invalid_food]}
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert "restaurant:no-meal-window" not in {
        candidate.place_id for candidate in output.food
    }
