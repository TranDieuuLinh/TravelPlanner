from app.modules.place_checker.scoring.service import CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    NOW,
    candidate,
    empty_places,
    retrieval,
)


def test_tie_break_is_deterministic() -> None:
    service = CandidateScoringService(now=NOW)
    batch = retrieval(candidate("b"), candidate("a"))

    first = service.rank(batch, analysis_context(), empty_places())
    second = service.rank(batch, analysis_context(), empty_places())

    assert [item.candidate.candidate_key for item in first.ranked] == [
        item.candidate.candidate_key for item in second.ranked
    ]
    assert first.ranked[0].candidate.candidate_key == "a"


def test_reserve_limit_caps_each_gap() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("a"), candidate("b"), candidate("c")),
        analysis_context(),
        empty_places(),
        reserve_limit_per_gap=2,
    )

    assert len(result.ranked) == 2


def test_default_reserve_grows_with_trip_days() -> None:
    context = analysis_context().model_copy(update={"days": 4})
    result = CandidateScoringService(now=NOW).rank(
        retrieval(*(candidate(str(index)) for index in range(8))),
        context,
        empty_places(),
    )

    assert result.reserve_limit_per_gap == 60
    assert result.pool_target == 95
    assert len(result.ranked) == 8


def test_global_ranking_can_exceed_per_gap_limit() -> None:
    first_gap = retrieval(*(candidate(f"first-{index}") for index in range(6)))
    second_gap = retrieval(*(candidate(f"second-{index}") for index in range(6)))
    second_gap = second_gap.model_copy(
        update={
            "gaps": [
                second_gap.gaps[0].model_copy(
                    update={
                        "gap_id": "gap:second",
                        "candidates": [
                            item.model_copy(update={"gap_id": "gap:second"})
                            for item in second_gap.gaps[0].candidates
                        ],
                    }
                )
            ]
        }
    )
    batch = first_gap.model_copy(update={"gaps": [*first_gap.gaps, *second_gap.gaps]})

    result = CandidateScoringService(now=NOW).rank(
        batch,
        analysis_context().model_copy(update={"days": 5}),
        empty_places(),
    )

    assert len(result.ranked) == 12
    assert result.ranked[-1].rank == 12


def test_pool_category_balancing_keeps_discovery_groups_in_pool() -> None:
    groups = [
        "food",
        "drink",
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
    result = CandidateScoringService().rank(
        retrieval(
            *[
                candidate(
                    f"{index}-{group}",
                    pool_category=group,
                    category="travel_place",
                )
                for group in groups
                for index in range(2)
            ]
        ),
        analysis_context().model_copy(update={"days": 1}),
        empty_places(),
        reserve_limit_per_gap=20,
        max_total_candidates=12,
    )

    selected_groups = {item.candidate.pool_category for item in result.ranked}
    assert len(result.ranked) == 12
    assert selected_groups == set(groups)
