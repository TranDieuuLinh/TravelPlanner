from app.modules.place_checker.scoring import CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    candidate,
    empty_places,
    retrieval,
)


def test_three_days_keep_thirty_six_candidates_of_each_type() -> None:
    travel = [
        candidate(f"travel-{index}", category="travel_place")
        for index in range(40)
    ]
    restaurants = [
        candidate(f"restaurant-{index}", category="restaurant")
        for index in range(40)
    ]

    result = CandidateScoringService().rank(
        retrieval(*travel, *restaurants),
        analysis_context(days=3),
        empty_places(),
    )

    categories = [item.candidate.category for item in result.ranked]
    assert result.pool_target == 72
    assert categories.count("travel_place") == 36
    assert categories.count("restaurant") == 36


def test_existing_places_reduce_only_their_own_type_quota() -> None:
    from app.modules.place_checker.tests.analysis_fixtures import (
        evaluated_place,
        place_batch,
    )

    existing = place_batch(
        evaluated_place("existing-travel", category="travel_place")
    )
    travel = [
        candidate(f"travel-{index}", category="travel_place")
        for index in range(12)
    ]
    restaurants = [
        candidate(f"restaurant-{index}", category="restaurant")
        for index in range(12)
    ]

    result = CandidateScoringService().rank(
        retrieval(*travel, *restaurants),
        analysis_context(days=1),
        existing,
    )

    categories = [item.candidate.category for item in result.ranked]
    assert categories.count("travel_place") == 11
    assert categories.count("restaurant") == 12


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
