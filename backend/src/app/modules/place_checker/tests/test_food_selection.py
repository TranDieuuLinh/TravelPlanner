import asyncio

from app.modules.place_checker.food_selection import FoodRestaurantSelectionService
from app.modules.place_checker.food_selection_contract import (
    FoodRestaurantCandidate,
    FoodSelectionAnchor,
)
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.shared.tools.bayesian_rating import bayesian_rating
from app.shared.contracts.place import Coordinates


class FakeFoodSource:
    def __init__(self, candidates: list[FoodRestaurantCandidate]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[str, list[str]]] = []

    async def find_food_restaurants(self, *, adm_id, anchor_place_ids):
        self.calls.append((adm_id, anchor_place_ids))
        return self.candidates


def candidate(
    anchor: str,
    restaurant: str,
    *,
    food: str = "food:pho",
    rating: float | None = 4.7,
    reviews: int | None = 100,
    priority: float = 0.9,
    distance: float = 0.5,
    match_type: str = "direct_id",
    match_confidence: float = 1.0,
) -> FoodRestaurantCandidate:
    food_name = "Phở" if food == "food:pho" else "Bún chả"
    return FoodRestaurantCandidate(
        anchor_place_id=anchor,
        food_item_id=food,
        food_item_name=food_name,
        food_priority=priority,
        food_confidence=0.9,
        offered_food_item_id=food,
        offered_food_item_name=food_name,
        food_match_type=match_type,
        food_match_confidence=match_confidence,
        restaurant_id=restaurant,
        restaurant_name=f"Restaurant {restaurant}",
        offer_confidence=0.95,
        distance_km=distance,
        threshold_km=2,
        metadata=PlaceMetadata(
            place_id=restaurant,
            coordinates=Coordinates(latitude=21.03, longitude=105.84),
            category="restaurant",
            tags=["restaurant"],
            rating=rating,
            review_count=reviews,
            typical_duration_minutes=60,
            typical_cost=50_000,
            cost_currency="VND",
            opening_hours=["07:00-21:00"],
        ),
    )


def test_bayesian_rating_keeps_sparse_candidate_instead_of_rejecting_it() -> None:
    score = bayesian_rating(
        rating=5,
        review_count=1,
        prior_mean=4.2,
        prior_weight=20,
    )

    assert score == 4.238095


def test_one_restaurant_is_selected_for_each_anchor() -> None:
    source = FakeFoodSource(
        [
            candidate("place:lake", "restaurant:pho"),
            candidate(
                "place:temple",
                "restaurant:bun-cha",
                food="food:bun-cha",
            ),
        ]
    )
    service = FoodRestaurantSelectionService(source)

    result = asyncio.run(
        service.select(
            analysis_context(),
            [
                FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm"),
                FoodSelectionAnchor(place_id="place:temple", name="Văn Miếu"),
            ],
        )
    )

    assert len(result.selections) == 2
    assert result.unmatched_anchor_place_ids == []
    assert all(
        item.selection_reason == "sole_candidate_for_food"
        for item in result.selections
    )
    assert all(item.food_match_type == "direct_id" for item in result.selections)
    assert all(item.food_match_confidence == 1 for item in result.selections)


def test_reliable_restaurant_beats_five_star_candidate_with_one_review() -> None:
    source = FakeFoodSource(
        [
            candidate(
                "place:lake",
                "restaurant:reliable",
                rating=4.8,
                reviews=2_000,
            ),
            candidate(
                "place:lake",
                "restaurant:sparse",
                rating=5.0,
                reviews=1,
            ),
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections[0].restaurant_id == "restaurant:reliable"
    assert result.selections[0].selection_reason == "bayesian_ranked"


def test_restaurant_reuse_is_only_a_fallback_when_no_unused_option_exists() -> None:
    source = FakeFoodSource(
        [
            candidate("place:a", "restaurant:shared"),
            candidate("place:b", "restaurant:shared", priority=0.95),
            candidate("place:b", "restaurant:other", priority=0.8),
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [
                FoodSelectionAnchor(place_id="place:a", name="A"),
                FoodSelectionAnchor(place_id="place:b", name="B"),
            ],
        )
    )

    assert [item.restaurant_id for item in result.selections] == [
        "restaurant:shared",
        "restaurant:other",
    ]


def test_special_exact_id_match_beats_offer_item_fallback() -> None:
    source = FakeFoodSource(
        [
            candidate(
                "place:lake",
                "restaurant:fallback",
                priority=0.35,
                match_type="offer_item_fallback",
            ),
            candidate("place:lake", "restaurant:direct"),
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections[0].restaurant_id == "restaurant:direct"
    assert result.selections[0].food_match_type == "direct_id"


def test_offer_item_fallback_is_preserved_in_selection_provenance() -> None:
    source = FakeFoodSource(
        [
            candidate(
                "place:lake",
                "restaurant:fallback",
                match_type="offer_item_fallback",
            )
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections[0].food_match_type == "offer_item_fallback"
    assert result.selections[0].offered_food_item_id == "food:pho"
