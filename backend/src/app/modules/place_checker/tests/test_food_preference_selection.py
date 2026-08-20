import asyncio

from app.modules.place_checker.selection.food.service import FoodRestaurantSelectionService
from app.modules.place_checker.selection.food.contract import FoodSelectionAnchor
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_food_selection import (
    FakeFoodSource,
    candidate,
)


def test_short_preference_is_ranked_before_food_quality_tiebreaks() -> None:
    preferred = candidate(
        "place:lake",
        "restaurant:local",
        rating=4.2,
        reviews=100,
    )
    preferred = preferred.model_copy(
        update={
            "metadata": preferred.metadata.model_copy(update={"tags": ["địa phương"]})
        }
    )
    source = FakeFoodSource(
        [
            candidate("place:lake", "restaurant:popular", rating=4.9, reviews=5_000),
            preferred,
        ]
    )
    context = analysis_context().model_copy(update={"preferences": ["địa phương"]})

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            context,
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections[0].restaurant_id == "restaurant:local"
