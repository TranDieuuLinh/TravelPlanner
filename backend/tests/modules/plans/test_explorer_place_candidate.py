import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import PlaceCandidateHint
from app.modules.plans.explorer.schema import ExploreResponse, FullExploreRequest


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


def test_explorer_output_separates_food_places_and_omits_debug() -> None:
    response = ExploreResponse.model_validate(
        {
            "intent": {"destination": "Hội An"},
            "tripSpec": {"days": 2},
            "placeCandidates": [
                {"name": "Chùa Cầu", "category": "attraction"},
                {"name": "Bánh mì Phượng", "category": "food"},
            ],
            "foodPlaces": [
                {"name": "Faifo Coffee", "category": "cafe"},
                {"name": "Phố cổ Hội An", "category": "attraction"},
            ],
            "debug": {"transcript": "must not leak into the response"},
        }
    )

    payload = response.model_dump(mode="json", by_alias=True)

    assert [place["name"] for place in payload["placeCandidates"]] == [
        "Chùa Cầu",
        "Phố cổ Hội An",
    ]
    assert [place["name"] for place in payload["foodPlaces"]] == [
        "Bánh mì Phượng",
        "Faifo Coffee",
    ]
    assert "debug" not in payload
