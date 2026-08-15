from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.modules.place_checker.scoring import CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    candidate,
    empty_places,
    retrieval,
)


def test_three_days_keep_forty_two_activities_and_thirty_food_candidates() -> None:
    travel = [
        candidate(f"travel-{index}", category="travel_place") for index in range(50)
    ]
    restaurants = [
        candidate(f"restaurant-{index}", category="restaurant") for index in range(40)
    ]

    result = CandidateScoringService().rank(
        retrieval(*travel, *restaurants),
        analysis_context(days=3),
        empty_places(),
    )

    categories = [item.candidate.category for item in result.ranked]
    assert result.pool_target == 77
    assert categories.count("travel_place") == 42
    assert categories.count("restaurant") == 30


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
    assert categories.count("travel_place") == 13
    assert categories.count("restaurant") == 10


def test_full_existing_pool_does_not_select_extra_candidates() -> None:
    from app.modules.place_checker.tests.analysis_fixtures import (
        evaluated_place,
        place_batch,
    )

    existing = place_batch(
        *(evaluated_place(f"existing-{index}") for index in range(14))
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
    assert len(result.ranked) == 14
    assert len(selected_ids & {item.candidate_key for item in special}) >= 6
    assert len(selected_ids & {item.candidate_key for item in popular}) >= 4


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
