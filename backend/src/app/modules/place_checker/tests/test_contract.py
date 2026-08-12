from decimal import Decimal

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
                "address_hint": None,
                "confidence": 0.98,
                "source_places": [
                    {
                        "origin": "input",
                        "evidence_type": "raw_prompt",
                        "source_url": None,
                        "evidence": "I want to visit Ho Chi Minh Mausoleum",
                        "source_time_hint": None,
                        "address_hint": None,
                    }
                ],
            }
        ],
        "input_items": [
            {
                "name": "pho",
                "item_type": "food",
                "action": "eat",
                "evidence": "eat pho",
                "confidence": 0.97,
            }
        ],
        "url_notes": None,
        "days": 4,
        "budget": {
            "level": "low",
            "target_amount": None,
            "currency": "VND",
            "source": "raw_prompt",
        },
        "people": {"adults": 1, "children": 0, "infants": 0},
        "short_preferences": [],
        "short_avoids": ["nightlife"],
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


def test_target_amount_requires_currency() -> None:
    raw = sample_payload()
    raw["budget"]["target_amount"] = Decimal("1000000")
    raw["budget"]["currency"] = None

    with pytest.raises(ValidationError):
        PlaceCheckerInput.model_validate(raw)


def test_malformed_candidate_becomes_validation_issue() -> None:
    raw = sample_payload()
    raw["places"].append({"name": "Broken", "confidence": 2})

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
                "addressHint": "49 Bát Đàn, Hoàn Kiếm, Hà Nội",
                "confidence": 0.97,
                "sourcePlaces": [
                    {
                        "origin": "url",
                        "evidenceType": "frame_ocr",
                        "sourceUrl": "https://www.example.com/video",
                        "evidence": "49 Bát Đàn, Hoàn Kiếm, Hà Nội",
                        "sourceTimeHint": None,
                        "addressHint": "49 Bát Đàn, Hoàn Kiếm, Hà Nội",
                        "observedAt": "2026-08-11T10:00:00Z",
                    }
                ],
            }
        ],
        "inputItems": [
            {
                "name": "phở",
                "itemType": "food",
                "action": "eat",
                "relatedPlaceName": "Phở Gia Truyền Bát Đàn",
                "evidence": "ăn phở tại Phở Gia Truyền Bát Đàn",
                "confidence": 0.98,
            }
        ],
        "urlNotes": [
            {
                "summary": "Nguồn giới thiệu phở bò.",
                "placeName": "Phở Gia Truyền Bát Đàn",
                "evidenceType": "transcript",
                "sourceUrl": "https://www.example.com/video",
                "observedAt": "2026-08-11T10:00:00Z",
            }
        ],
        "days": 4,
        "budget": {
            "level": "low",
            "targetAmount": 6000000,
            "currency": "VND",
            "source": "raw_prompt",
        },
        "people": {"adults": 2, "children": 0, "infants": 0},
        "shortPreferences": ["local_food"],
        "shortAvoids": ["nightlife"],
    }

    payload = PlaceCheckerInput.model_validate(raw)
    serialized = payload.model_dump(by_alias=True, exclude={"validation_issues"})

    assert payload.input_adm == "Hanoi"
    assert payload.input_items[0].related_place_name == "Phở Gia Truyền Bát Đàn"
    assert payload.places[0].source_places[0].observed_at is not None
    assert payload.url_notes[0].observed_at is not None
    assert payload.budget.target_amount == Decimal("6000000")
    assert serialized["inputADM"] == "Hanoi"
    assert serialized["inputItems"][0]["relatedPlaceName"] == "Phở Gia Truyền Bát Đàn"
