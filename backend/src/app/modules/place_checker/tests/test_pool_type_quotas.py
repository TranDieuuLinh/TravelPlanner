from app.modules.place_checker.planning.category import (
    planner_category,
    planner_category_for_candidate,
)
from app.modules.place_checker.selection.pool_balancing import CandidatePoolBalancer
from app.modules.place_checker.scoring.service import CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    candidate,
    empty_places,
    retrieval,
)


def test_three_days_keep_independent_entity_quotas() -> None:
    candidates = [
        *(candidate(f"travel-{index}", category="travel_place") for index in range(50)),
        *(candidate(f"food-{index}", category="restaurant") for index in range(40)),
        *(candidate(f"drink-{index}", category="drink_dessert") for index in range(20)),
        *(
            candidate(f"evening-{index}", category="entertainment")
            for index in range(20)
        ),
    ]

    result = CandidateScoringService().rank(
        retrieval(*candidates), analysis_context(days=3), empty_places()
    )

    categories = [item.candidate.category for item in result.ranked]
    assert result.pool_target == 72
    assert categories.count("travel_place") == 36
    assert categories.count("restaurant") == 18
    assert categories.count("drink_dessert") == 9
    assert categories.count("entertainment") == 6
    assert len({item.candidate.candidate_key for item in result.ranked}) == 69


def test_existing_places_reduce_only_their_entity_quota() -> None:
    from app.modules.place_checker.tests.analysis_fixtures import (
        evaluated_place,
        place_batch,
    )

    existing = place_batch(evaluated_place("existing", category="travel_place"))
    candidates = [
        *(candidate(f"travel-{index}", category="travel_place") for index in range(20)),
        *(candidate(f"food-{index}", category="restaurant") for index in range(12)),
    ]

    result = CandidateScoringService().rank(
        retrieval(*candidates), analysis_context(days=1), existing
    )

    categories = [item.candidate.category for item in result.ranked]
    assert categories.count("travel_place") == 11
    assert categories.count("restaurant") == 6


def test_missing_duration_cannot_consume_a_pool_slot() -> None:
    missing = candidate("missing", category="travel_place")
    missing = missing.model_copy(
        update={
            "metadata": missing.metadata.model_copy(
                update={"typical_duration_minutes": None}
            )
        }
    )

    result = CandidateScoringService().rank(
        retrieval(missing), analysis_context(days=1), empty_places()
    )

    assert result.ranked == []
    assert result.excluded[0].exclusion_reasons == ["missing_duration"]


def test_accommodation_pool_is_capped_at_three_for_the_trip() -> None:
    hotels = [
        candidate(f"hotel-{index}", category="accommodation") for index in range(8)
    ]
    hotels = [
        item.model_copy(
            update={
                "metadata": item.metadata.model_copy(
                    update={"typical_duration_minutes": None}
                )
            }
        )
        for item in hotels
    ]

    result = CandidateScoringService().rank(
        retrieval(*hotels), analysis_context(days=3), empty_places()
    )

    assert len(result.ranked) == 3
    assert all(item.candidate.category == "accommodation" for item in result.ranked)


def test_cafe_is_a_separate_drink_dessert_pool() -> None:
    assert planner_category("cafe") == "drink_dessert"
    assert planner_category("DrinkDessert") == "drink_dessert"
    assert CandidatePoolBalancer._entity_type("cafe") == "drink_dessert"
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Cafe Test",
            tags=["đồ uống"],
        )
        == "drink_dessert"
    )


def test_obvious_venue_names_are_reclassified_after_identity_resolution() -> None:
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="ON TOP MUSIC BOX",
            tags=[],
        )
        == "entertainment"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Quán Mì Vằn Thắn, Sủi Cảo Gia Truyền",
            tags=[],
        )
        == "restaurant"
    )
    assert (
        planner_category_for_candidate(
            "restaurant",
            name="Phố đi bộ trung tâm",
            tags=[],
        )
        == "travel_place"
    )


def test_art_center_provider_context_is_reclassified_as_entertainment() -> None:
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Mango Art - Vẽ Cả thế giới",
            tags=[],
            context=(
                "Mango Art - Vẽ Cả thế giới thuộc danh mục Art center; "
                "mô tả tối thiểu được tạo từ dữ liệu nguồn."
            ),
        )
        == "entertainment"
    )


def test_pho_food_marker_does_not_confuse_pho_street_with_noodles() -> None:
    assert (
        planner_category_for_candidate(
            "entertainment",
            name="Music Box Phố Vọng",
            tags=[],
        )
        == "entertainment"
    )
    assert (
        planner_category_for_candidate(
            "entertainment",
            name="HDRADIO Phố Vọng - Audio & Home Cinema & Karaoke",
            tags=[],
        )
        == "entertainment"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Phố cổ Hà Nội",
            tags=[],
        )
        == "travel_place"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Phở Bát Đàn",
            tags=[],
        )
        == "restaurant"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Pho Thin",
            tags=[],
        )
        == "restaurant"
    )
