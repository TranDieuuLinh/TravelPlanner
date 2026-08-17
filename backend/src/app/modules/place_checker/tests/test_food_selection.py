import asyncio

from app.modules.place_checker.food_selection import FoodRestaurantSelectionService
from app.modules.place_checker.food_candidate_policy import FoodCandidatePolicy
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
        self.calls: list[dict] = []

    async def find_food_restaurants(
        self,
        *,
        adm_id,
        anchor_place_ids,
        radius_km=5.0,
        per_anchor_limit=8,
        excluded_restaurant_ids=None,
        required_meals=None,
    ):
        self.calls.append(
            {
                "adm_id": adm_id,
                "anchor_place_ids": anchor_place_ids,
                "radius_km": radius_km,
                "per_anchor_limit": per_anchor_limit,
                "required_meals": required_meals or [],
            }
        )
        excluded = set(excluded_restaurant_ids or [])
        return [
            item for item in self.candidates if item.restaurant_id not in excluded
        ]


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
    style_id: str | None = None,
    style_name: str | None = None,
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
        style_id=style_id,
        style_name=style_name,
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
    assert source.calls[0]["radius_km"] == 5.0
    assert source.calls[1]["radius_km"] is None


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


def test_food_reputation_is_separate_and_drinkdessert_is_downweighted() -> None:
    restaurant = candidate("place:a", "restaurant:a", reviews=100_000)
    drink = candidate("place:b", "drink:b", reviews=100_000).model_copy(
        update={
            "metadata": restaurant.metadata.model_copy(
                update={"place_id": "drink:b", "category": "drink_dessert"}
            )
        }
    )
    policy = FoodCandidatePolicy()
    priors = policy.priors([restaurant, drink])

    assert policy.pair_score(restaurant, priors) > policy.pair_score(drink, priors)


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


def test_deduplicates_same_restaurant_per_anchor_before_selection() -> None:
    source = FakeFoodSource(
        [
            candidate(
                "place:lake",
                "restaurant:shared",
                priority=0.35,
                match_type="offer_item_fallback",
            ),
            candidate("place:lake", "restaurant:shared", priority=0.9),
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert len(result.selections) == 1
    assert result.selections[0].food_match_type == "direct_id"


def test_merges_relationships_when_restaurant_is_near_multiple_anchors() -> None:
    source = FakeFoodSource(
        [
            candidate("place:lake", "restaurant:shared", distance=0.4),
            candidate("place:temple", "restaurant:shared", distance=1.2),
        ]
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(days=1),
            [
                FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm"),
                FoodSelectionAnchor(place_id="place:temple", name="Văn Miếu"),
            ],
        )
    )

    assert len(result.selections) == 1
    assert result.selections[0].related_anchor_place_ids == [
        "place:lake",
        "place:temple",
    ]


def test_general_adm_is_not_queried_when_soft_reserve_is_complete() -> None:
    source = FakeFoodSource(
        [candidate("place:lake", f"restaurant:{index}") for index in range(12)]
    )

    asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(days=2),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert [call["radius_km"] for call in source.calls] == [5.0]


def test_general_adm_fills_only_the_soft_reserve_deficit() -> None:
    near = [candidate("place:lake", f"restaurant:near:{index}") for index in range(7)]
    general = [
        candidate("place:lake", f"restaurant:general:{index}").model_copy(
            update={"proximity_source": "general_adm", "distance_km": None}
        )
        for index in range(5)
    ]

    class ReserveFoodSource(FakeFoodSource):
        async def find_food_restaurants(self, **kwargs):
            self.calls.append(kwargs)
            return near if kwargs["radius_km"] is not None else general

    source = ReserveFoodSource([])
    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(days=2),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert len(result.selections) == 12
    assert sum(
        item.proximity_source == "general_adm" for item in result.selections
    ) == 5
    assert [call["radius_km"] for call in source.calls] == [5.0, None]
    assert source.calls[1]["per_anchor_limit"] == 7
    assert set(source.calls[1]["required_meals"]) == {
        "breakfast",
        "lunch",
        "dinner",
    }


def test_filters_incomplete_restaurant_before_selection() -> None:
    incomplete = candidate("place:lake", "restaurant:incomplete", priority=0.99)
    incomplete = incomplete.model_copy(
        update={
            "metadata": incomplete.metadata.model_copy(
                update={"typical_duration_minutes": None}
            )
        }
    )
    complete = candidate("place:lake", "restaurant:complete", priority=0.8)
    source = FakeFoodSource([incomplete, complete])

    result = asyncio.run(
        FoodRestaurantSelectionService(source).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections[0].restaurant_id == "restaurant:complete"
    assert result.warnings == [
        "Đã loại candidate quán không đủ dữ liệu trước selection: missing_duration=1.",
        "Food meal matching không đủ hard coverage: "
        "hard_missing=5, reserve_missing=6.",
    ]


def test_incomplete_restaurant_leaves_anchor_unmatched() -> None:
    incomplete = candidate("place:lake", "restaurant:incomplete")
    incomplete = incomplete.model_copy(
        update={
            "metadata": incomplete.metadata.model_copy(update={"opening_hours": None})
        }
    )

    result = asyncio.run(
        FoodRestaurantSelectionService(FakeFoodSource([incomplete])).select(
            analysis_context(),
            [FoodSelectionAnchor(place_id="place:lake", name="Hồ Gươm")],
        )
    )

    assert result.selections == []
    assert result.unmatched_anchor_place_ids == ["place:lake"]
    assert result.warnings == [
        "Không tìm thấy quán phù hợp gần 1 điểm tham quan.",
        "Đã loại candidate quán không đủ dữ liệu trước selection: "
        "missing_meal_window=1.",
        "Food meal matching không đủ hard coverage: "
        "hard_missing=6, reserve_missing=6.",
    ]
