import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import PlaceCandidateHint
from app.modules.plans.explorer.place_candidate_aggregator import (
    PlaceCandidateAggregator,
)
from app.modules.plans.explorer.schema import (
    FullExploreRequest,
    UnifiedPlaceCandidate,
)


def test_place_candidate_serializes_category_in_api_shape() -> None:
    candidate = PlaceCandidateHint(name="Bánh mì Phượng", category="food")

    assert candidate.model_dump(mode="json", by_alias=True)["category"] == "food"


def test_place_candidate_defaults_unknown_category_to_other() -> None:
    candidate = PlaceCandidateHint(name="Địa điểm chưa rõ")

    assert candidate.model_dump(mode="json", by_alias=True)["category"] == "other"


def test_place_candidate_rejects_category_outside_contract() -> None:
    with pytest.raises(ValidationError):
        PlaceCandidateHint(name="Địa điểm", category="shopping")


def test_explorer_input_accepts_user_travel_style() -> None:
    request = FullExploreRequest.model_validate(
        {
            "rawRequest": "Đà Nẵng 3 ngày",
            "destination": "Đà Nẵng",
            "userState": {
                "travelStyle": "adventure",
                "travelPreferences": ["local food"],
            },
        }
    )

    assert request.user_state.travel_style == "adventure"
    assert request.model_dump(mode="json", by_alias=True)["userState"][
        "travelStyle"
    ] == "adventure"


def test_explorer_aggregates_all_categories_into_one_candidate_array() -> None:
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Hội An",
        generated=[
            UnifiedPlaceCandidate(
                name="Chùa Cầu",
                category="attraction",
                sources=[{"type": "user_prompt", "url": None}],
                confidence=1,
            ),
            UnifiedPlaceCandidate(
                name="Bánh mì Phượng",
                category="food",
                sources=[
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                confidence=0.8,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert [candidate.name for candidate in candidates] == [
        "Chùa Cầu",
        "Bánh mì Phượng",
    ]
    assert candidates[1].category.value == "food"
    assert candidates[1].sources[0].url == "https://example.com/reel"


def test_explorer_merges_duplicate_candidates_and_preserves_sources() -> None:
    candidates = PlaceCandidateAggregator().aggregate(
        destination="Đà Nẵng",
        generated=[
            UnifiedPlaceCandidate(
                name="Bà Nà Hills",
                category="attraction",
                sources=[{"type": "ocr", "url": None}],
                confidence=0.7,
            ),
            UnifiedPlaceCandidate(
                name="Ba Na Hills",
                category="attraction",
                sources=[
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                confidence=0.9,
            ),
        ],
        explicit=[],
        url_results=[],
    )

    assert len(candidates) == 1
    assert {source.type.value for source in candidates[0].sources} == {
        "ocr",
        "url",
    }
