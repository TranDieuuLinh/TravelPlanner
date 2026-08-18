from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.modules.place_checker.activity_pool_selection import select_activity_coverage
from app.modules.place_checker.planner_category import (
    planner_category,
    planner_category_for_candidate,
)
from app.modules.place_checker.pool_balancing import CandidatePoolBalancer
from app.modules.place_checker.scoring import CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    candidate,
    empty_places,
    retrieval,
)


def test_three_days_keep_independent_place_food_and_entertainment_quotas() -> None:
    travel = [
        candidate(f"travel-{index}", category="travel_place") for index in range(50)
    ]
    restaurants = [
        candidate(f"restaurant-{index}", category="restaurant") for index in range(40)
    ]
    entertainment = [
        candidate(f"entertainment-{index}", category="entertainment")
        for index in range(20)
    ]

    result = CandidateScoringService().rank(
        retrieval(*travel, *restaurants, *entertainment),
        analysis_context(days=3),
        empty_places(),
    )

    categories = [item.candidate.category for item in result.ranked]
    assert result.pool_target == 137
    assert categories.count("travel_place") == 50
    assert categories.count("restaurant") == 40
    assert categories.count("entertainment") == 18


def test_existing_places_reduce_only_their_own_type_quota() -> None:
    from app.modules.place_checker.tests.analysis_fixtures import (
        evaluated_place,
        place_batch,
    )

    existing = place_batch(evaluated_place("existing-travel", category="travel_place"))
    travel = [
        candidate(f"travel-{index}", category="travel_place") for index in range(20)
    ]
    restaurants = [
        candidate(f"restaurant-{index}", category="restaurant") for index in range(12)
    ]

    result = CandidateScoringService().rank(
        retrieval(*travel, *restaurants),
        analysis_context(days=1),
        existing,
    )

    categories = [item.candidate.category for item in result.ranked]
    assert categories.count("travel_place") == 20
    assert categories.count("restaurant") == 12


def test_full_existing_pool_does_not_select_extra_candidates() -> None:
    from app.modules.place_checker.tests.analysis_fixtures import (
        evaluated_place,
        place_batch,
    )

    existing = place_batch(
        *(evaluated_place(f"existing-{index}") for index in range(22))
    )
    result = CandidateScoringService().rank(
        retrieval(
            *(candidate(f"new-{index}", category="travel_place") for index in range(5))
        ),
        analysis_context(days=1),
        existing,
    )

    assert result.ranked == []


def test_activity_reserve_covers_special_and_popular_candidates() -> None:
    relation = PlaceRelationshipEvidence(
        relationship_type="Special_Experience",
        direction="area_to_place",
        scope="destination",
        from_entity_id="adm:hanoi",
        to_entity_id="special",
        related_entity_id="special",
        score=0.9,
    )
    special = [
        candidate(f"special-{index}", category="travel_place").model_copy(
            update={"relationships": [relation]}
        )
        for index in range(8)
    ]
    popular = []
    for index in range(8):
        item = candidate(f"popular-{index}", category="travel_place")
        popular.append(
            item.model_copy(
                update={
                    "metadata": item.metadata.model_copy(
                        update={"rating": 4.8, "review_count": 20_000 - index}
                    )
                }
            )
        )
    general = [
        candidate(f"general-{index}", category="travel_place") for index in range(12)
    ]

    result = CandidateScoringService().rank(
        retrieval(*special, *popular, *general),
        analysis_context(days=1),
        empty_places(),
    )

    selected_ids = {item.candidate.candidate_key for item in result.ranked}
    assert len(result.ranked) == 22
    assert len(selected_ids & {item.candidate_key for item in special}) == 8
    assert len(selected_ids & {item.candidate_key for item in popular}) >= 7


def test_activity_reserve_keeps_available_knowledge_tags() -> None:
    groups = [
        "culture",
        "nature",
        "shopping",
        "nightlife",
        "workshop",
        "performance",
        "outdoor",
        "family",
        "special_experience",
        "local_activity",
    ]
    themed = [
        candidate(
            f"theme-{group}",
            category="travel_place",
            tags=[group],
            pool_category=group,
        )
        for group in groups
    ]
    styled = candidate("styled", category="travel_place").model_copy(
        update={"tags": ["relaxing"]}
    )
    dominant = [
        candidate(f"dominant-{index}", category="travel_place") for index in range(20)
    ]

    result = CandidateScoringService().rank(
        retrieval(*dominant, *themed, styled),
        analysis_context(days=1),
        empty_places(),
        reserve_limit_per_gap=60,
    )

    selected_ids = {item.candidate.candidate_key for item in result.ranked}
    assert {item.candidate_key for item in themed} <= selected_ids
    assert styled.candidate_key in selected_ids


def test_candidate_without_duration_cannot_fill_a_planner_pool_slot() -> None:
    missing_duration = candidate("missing-duration", category="travel_place")
    missing_duration = missing_duration.model_copy(
        update={
            "metadata": missing_duration.metadata.model_copy(
                update={"typical_duration_minutes": None}
            )
        }
    )

    result = CandidateScoringService().rank(
        retrieval(missing_duration),
        analysis_context(days=1),
        empty_places(),
    )

    assert result.ranked == []
    assert result.excluded[0].exclusion_reasons == ["missing_duration"]


def test_accommodation_pool_keeps_five_candidates_for_percentile_selection() -> None:
    accommodations = [
        candidate(f"hotel-{index}", category="accommodation") for index in range(10)
    ]
    accommodations = [
        item.model_copy(
            update={
                "metadata": item.metadata.model_copy(
                    update={"typical_duration_minutes": None}
                )
            }
        )
        for item in accommodations
    ]

    result = CandidateScoringService().rank(
        retrieval(*accommodations),
        analysis_context(days=3),
        empty_places(),
    )

    assert len(result.ranked) == 5
    assert all(item.candidate.category == "accommodation" for item in result.ranked)


def test_cafe_category_is_not_counted_as_travel_place() -> None:
    assert planner_category("cafe") == "drink_dessert"
    assert planner_category("DrinkDessert") == "drink_dessert"
    assert CandidatePoolBalancer._entity_type("cafe") == "entertainment"


def test_obvious_leisure_name_cannot_masquerade_as_travel_place() -> None:
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="ON TOP MUSIC BOX",
            tags=["travel_place"],
        )
        == "entertainment"
    )
    assert (
        CandidatePoolBalancer._entity_type(
            "travel_place",
            name="SG Golf Mỹ Đình",
            tags=["travel_place"],
        )
        == "entertainment"
    )
    for name in (
        "Manup Ngõ 2 Nguyễn Viết Xuân & Sân chơi bi-a chuyên nghiệp",
        "Ngọt Studio - Chụp ảnh cho bé Hà Nội",
        "An An Entertainment",
        "Nguyễn Khương - Giải cơ đau vai gáy lưng hông chuyên sâu",
        "ELLY Trương Định Hoàng Mai Hà Nội",
        "Carpe Diem - Souvenir, Handcrafted Candles & Gifts",
        "Gói Gém Concept Store - Souvenirs by Local Artists",
        "Gói Gém Souvernirs, Gift & Local Art Store - Train Station",
        "CULCAT",
        "Garmin Aeon Mall Long Biên - Hà Nội",
        "Kính Mắt Việt Tín - Tasco Mall Long Biên",
        "Miniwood Design",
        "Hanoi Mood:ON Tây Sơn",
        "FOURT PILATES VINHOMES RIVERSIDE",
        "Gpt Guitar School",
        "Tẩm Quất Người Mù Khiếm Thị Dương Minh",
        "Khoa Cầu Đường, Trường ĐHXD Hà Nội - Faculty of Bridges and Roads",
        "TiredCity 05 Nhà Thờ",
        "TLT PICKLEBALL HOUSE",
        "Cửa hàng The Rare Rium- Plant & Moss Art",
        "Guitar Ba Đờn - Showroom Chính Hãng Hà Nội",
        "Vòng Hoa Nhà Tang Lễ Cầu Giấy Trần Vĩ",
        "Công Ty Tnhh Tinh Dầu Và Chất Thơm Ht",
    ):
        assert (
            planner_category_for_candidate(
                "travel_place",
                name=name,
                tags=["travel_place"],
            )
            == "entertainment"
        )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Thang Long Water Puppet Theatre",
            tags=["culture"],
        )
        == "travel_place"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="TiredCity 05 Nhà Thờ",
            tags=["travel_place"],
            pool_category="shopping",
        )
        == "entertainment"
    )
    assert (
        planner_category_for_candidate(
            "entertainment",
            name="Quán Mì Vằn Thắn, Sủi Cảo Gia Truyền",
            tags=["restaurant"],
        )
        == "restaurant"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Quán Mì Vằn Thắn, Sủi Cảo Gia Truyền",
            tags=["travel_place"],
        )
        == "restaurant"
    )
    assert (
        planner_category_for_candidate(
            "restaurant",
            name="Trà sữa Dee Thai",
            tags=["đồ_uống"],
        )
        == "drink_dessert"
    )
    assert (
        planner_category_for_candidate(
            "travel_place",
            name="Hanoi Creative Space",
            tags=["culture"],
        )
        == "travel_place"
    )
    for name, context in (
        ("Empty Wall Gallery", "thuộc danh mục Art supply store"),
        ("Thien y art gallery", "thuộc danh mục Artistic handicrafts"),
        ("Kính Hoa Đồng Gia Việt", "thuộc danh mục Stained glass studio"),
        ("Photosona", "thuộc danh mục Photo booth"),
        ("NOTH Garden", "thuộc danh mục Garden center"),
        ("Vườn của mẹ", "thuộc danh mục Interior plant service"),
        ("Trang Phục Biểu Diễn", "thuộc danh mục Costume rental service"),
    ):
        assert (
            planner_category_for_candidate(
                "travel_place",
                name=name,
                tags=["travel_place"],
                context=context,
            )
            == "entertainment"
        )


def test_activity_pool_soft_caps_repeated_broad_tags_when_alternatives_exist() -> None:
    culture = [
        candidate(f"culture-{index}", category="travel_place", tags=["culture"])
        for index in range(8)
    ]
    nature = [
        candidate(f"nature-{index}", category="travel_place", tags=["nature"])
        for index in range(8)
    ]
    shopping = [
        candidate(f"shopping-{index}", category="travel_place", tags=["shopping"])
        for index in range(8)
    ]
    ranked = CandidateScoringService().rank(
        retrieval(*culture, *nature, *shopping),
        analysis_context(days=1),
        empty_places(),
        reserve_limit_per_gap=60,
    ).ranked

    selected = select_activity_coverage(ranked, 9)
    selected_tags = [item.candidate.tags[0] for item in selected]

    assert selected_tags.count("culture") <= 3
    assert selected_tags.count("nature") >= 3
    assert selected_tags.count("shopping") >= 3
