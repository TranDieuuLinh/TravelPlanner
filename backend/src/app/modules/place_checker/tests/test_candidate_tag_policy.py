from collections import Counter

from app.modules.place_checker.scoring.service import CandidateScoringService
from app.modules.place_checker.scoring.tag_policy import CandidateTagPolicy
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.modules.place_checker.tests.test_scoring_reranking import (
    NOW,
    candidate,
    empty_places,
    retrieval,
)


def test_preference_is_divided_by_candidate_tag_count() -> None:
    context = analysis_context()
    context.preferences = ["Văn hóa"]
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate("half", tags=["Văn hóa", "kiến trúc"]),
            candidate(
                "quarter",
                tags=["Văn hóa", "kiến trúc", "lịch sử", "Tâm linh"],
            ),
        ),
        context,
        empty_places(),
    )
    by_id = {item.candidate.candidate_key: item for item in result.ranked}

    assert by_id["half"].components.preference_match == 0.5
    assert by_id["quarter"].components.preference_match == 0.25


def test_non_taxonomy_tag_does_not_change_preference_denominator() -> None:
    context = analysis_context()
    context.preferences = ["Văn hóa"]
    item = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("mixed", tags=["Văn hóa", "technical:internal"])),
        context,
        empty_places(),
    ).ranked[0]

    assert item.selection_tags == ["Văn hóa"]
    assert item.components.preference_match == 1


def test_tag_diversity_uses_diminishing_returns() -> None:
    tags = ["Văn hóa"]

    assert CandidateTagPolicy.diversity_ratio(tags, Counter()) == 1
    assert CandidateTagPolicy.diversity_ratio(tags, Counter({"Văn hóa": 1})) == 0.5
    assert round(
        CandidateTagPolicy.diversity_ratio(tags, Counter({"Văn hóa": 2})),
        6,
    ) == 0.333333


def test_tag_diversity_averages_all_candidate_tags() -> None:
    score = CandidateTagPolicy.diversity_ratio(
        ["Văn hóa", "kiến trúc"],
        Counter({"Văn hóa": 1}),
    )

    assert score == 0.75
