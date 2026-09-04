import pytest
from pydantic import ValidationError

from app.modules.place_checker.contract import (
    EvidenceOrigin,
    PlaceCheckerInput,
    SourceTier,
)


def sample_payload() -> dict:
    return {
        "input_ADM": "Hanoi",
        "places": [
            {
                "name": "Ho Chi Minh Mausoleum",
                "source_places": [
                    {
                        "evidence_type": "raw_prompt",
                        "source_url": None,
                        "source_time_hint": None,
                        "address_hint": None,
                        "url_notes": [],
                    }
                ],
                "latitude": None,
                "longitude": None,
            }
        ],
        "input_items": [
            {
                "name": "pho",
                "item_type": "food",
                "related_place_name": None,
            }
        ],
        "days": 4,
        "budget": {
            "amount_per_person": None,
            "currency": "VND",
            "level": "low",
        },
        "people": {"adults": 1, "children": 0, "infants": 0},
        "short_preferences": [],
        "short_avoids": ["nightlife"],
        "special_notes": [],
    }


def test_parses_current_explorer_payload() -> None:
    payload = PlaceCheckerInput.model_validate(sample_payload())

    assert payload.input_adm == "Hanoi"
    assert payload.url_notes == []
    assert payload.days == 4
    assert payload.budget.level == "low"
    assert payload.budget.target_amount is None
    assert payload.people.total == 1
    assert payload.places[0].source_tier == SourceTier.direct_user
    assert payload.places[0].source_places[0].origin == EvidenceOrigin.input
    assert payload.input_items[0].name == "pho"


def test_rejects_removed_explorer_source_runtime_metadata() -> None:
    raw = sample_payload()
    source = raw["places"][0]["source_places"][0]
    source.update(
        {
            "platform": "youtube",
            "extractor_version": "youtube-transcript-v7",
            "model_version": "gemini-2.5-flash",
            "cache_status": "bypassed",
        }
    )

    payload = PlaceCheckerInput.model_validate(raw)

    assert payload.places == []
    assert payload.validation_issues[0].code == "INVALID_PLACE_CANDIDATE"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("input_ADM",), " "),
        (("days",), 0),
        (("days",), 31),
        (("people", "adults"), -1),
        (("people", "adults"), 0),
    ],
)
def test_rejects_invalid_request_level_data(
    path: tuple[str, ...],
    value: object,
) -> None:
    raw = sample_payload()
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    if path == ("people", "adults") and value == -1:
        target["children"] = 1

    with pytest.raises(ValidationError):
        PlaceCheckerInput.model_validate(raw)


def test_rejects_invalid_currency() -> None:
    raw = sample_payload()
    raw["budget"]["amount_per_person"] = 1_000_000
    raw["budget"]["currency"] = "VN"

    with pytest.raises(ValidationError):
        PlaceCheckerInput.model_validate(raw)


def test_malformed_candidate_becomes_validation_issue() -> None:
    raw = sample_payload()
    raw["places"].append({"name": "Broken"})

    payload = PlaceCheckerInput.model_validate(raw)

    assert len(payload.places) == 1
    assert len(payload.validation_issues) == 1
    assert payload.validation_issues[0].name == "Broken"
    assert payload.validation_issues[0].code == "INVALID_PLACE_CANDIDATE"


def test_rejects_one_sided_coordinates_as_candidate_issue() -> None:
    raw = sample_payload()
    raw["places"][0]["latitude"] = 21.03

    payload = PlaceCheckerInput.model_validate(raw)

    assert payload.places == []
    assert payload.validation_issues[0].code == "INVALID_PLACE_CANDIDATE"


def test_forbids_itinerary_fields() -> None:
    raw = sample_payload()
    raw["day"] = 1

    with pytest.raises(ValidationError):
        PlaceCheckerInput.model_validate(raw)


def test_parses_locked_camel_case_explorer_contract() -> None:
    raw = {
        "inputADM": "Hanoi",
        "places": [
            {
                "name": "Phở Gia Truyền Bát Đàn",
                "sourcePlaces": [
                    {
                        "evidenceType": "url",
                        "sourceUrl": "https://www.example.com/video",
                        "sourceTimeHint": None,
                        "addressHint": "49 Bát Đàn, Hoàn Kiếm, Hà Nội",
                        "urlNotes": [{"summary": "Nguồn giới thiệu phở bò."}],
                    }
                ],
                "latitude": None,
                "longitude": None,
            }
        ],
        "inputItems": [
            {
                "name": "phở",
                "itemType": "food",
                "relatedPlaceName": "Phở Gia Truyền Bát Đàn",
            }
        ],
        "days": 4,
        "budget": {
            "amountPerPerson": 3_000_000,
            "currency": "VND",
            "level": "low",
        },
        "people": {"adults": 2, "children": 0, "infants": 0},
        "shortPreferences": ["local_food"],
        "shortAvoids": ["nightlife"],
        "specialNotes": [],
    }

    payload = PlaceCheckerInput.model_validate(raw)
    serialized = payload.model_dump(by_alias=True, exclude={"validation_issues"})

    assert payload.input_adm == "Hanoi"
    assert payload.input_items[0].related_place_name == "Phở Gia Truyền Bát Đàn"
    assert payload.url_notes[0].summary == "Nguồn giới thiệu phở bò."
    assert payload.budget.amount_per_person == 3_000_000
    assert serialized["inputADM"] == "Hanoi"
    assert serialized["inputItems"][0]["relatedPlaceName"] == "Phở Gia Truyền Bát Đàn"
    assert serialized["places"][0]["sourcePlaces"][0]["urlNotes"] == [
        {"summary": "Nguồn giới thiệu phở bò."}
    ]
    assert "tags" not in serialized["places"][0]
    assert "confidence" not in serialized["places"][0]
    assert "urlNotes" not in serialized
    assert set(serialized["budget"]) == {"amountPerPerson", "currency", "level"}
