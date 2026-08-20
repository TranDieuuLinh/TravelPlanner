from datetime import UTC, datetime

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.contract import (
    ExplorerApiOutput,
    ExplorerBudget,
    ExplorerCompleteness,
    ExplorerOutput,
    ExplorerPlace,
    PlaceSource,
    RequestedItem,
    SourceNote,
)


def test_api_output_keeps_only_compact_explorer_fields() -> None:
    observed_at = datetime(2026, 8, 20, tzinfo=UTC)
    internal = ExplorerOutput(
        status="ready",
        intakeId="intake-test",
        input_ADM="Đà Nẵng",
        places=[
            ExplorerPlace(
                name="Cầu Rồng",
                confidence=0.9,
                sourcePlaces=[
                    PlaceSource(
                        origin="url",
                        evidenceType="transcript",
                        sourceUrl="https://example.com/video",
                        evidence="Ghé Cầu Rồng vào buổi tối",
                        observedAt=observed_at,
                    ),
                    PlaceSource(
                        origin="url",
                        evidenceType="transcript",
                        sourceUrl="https://example.com/video",
                        evidence="Duplicate internal evidence",
                    ),
                ],
            )
        ],
        inputItems=[
            RequestedItem(
                name="mì Quảng",
                itemType="food",
                action="eat",
                relatedPlaceName="Mì Quảng Bà Mua",
                evidence="ăn mì Quảng ở Mì Quảng Bà Mua",
                confidence=0.95,
            )
        ],
        urlNotes=[
            SourceNote(
                summary="Xem Cầu Rồng phun lửa",
                evidenceType="transcript",
                sourceUrl="https://example.com/video",
                observedAt=observed_at,
            )
        ],
        budget=ExplorerBudget(
            level="medium",
            targetAmount=2_000_000,
            source="raw_prompt",
            basis="per_person",
        ),
        clarificationQuestion="internal-only",
        warnings=["internal-only"],
        completeness=ExplorerCompleteness(complete=True),
    )

    payload = ExplorerApiOutput.from_internal(
        internal, filter_tags=lambda values: values
    ).model_dump(mode="json", by_alias=True)

    assert set(payload) == {
        "intakeId",
        "input_ADM",
        "places",
        "inputItems",
        "days",
        "startDate",
        "timezone",
        "budget",
        "people",
        "shortPreferences",
        "shortAvoids",
        "specialNotes",
    }
    place = payload["places"][0]
    assert "confidence" not in place
    assert "tags" not in place
    assert place["sourcePlaces"] == [
        {
            "evidenceType": "url",
            "sourceUrl": "https://example.com/video",
            "sourceTimeHint": None,
            "addressHint": None,
            "urlNotes": [{"summary": "Xem Cầu Rồng phun lửa"}],
        }
    ]
    assert payload["inputItems"] == [{
        "name": "mì Quảng",
        "itemType": "food",
        "relatedPlaceName": "Mì Quảng Bà Mua",
    }]
    assert "urlNotes" not in place
    assert payload["budget"] == {
        "amountPerPerson": 2_000_000,
        "currency": "VND",
        "level": "medium",
    }


def test_api_evidence_type_maps_prompt_without_exposing_internal_provenance() -> None:
    internal = ExplorerOutput(
        status="ready",
        intakeId="intake-prompt",
        input_ADM="Huế",
        places=[
            ExplorerPlace(
                name="Đại Nội Huế",
                confidence=0.95,
                sourcePlaces=[
                    PlaceSource(
                        origin="input",
                        evidenceType="raw_prompt",
                        evidence="tham quan Đại Nội Huế",
                    )
                ],
            )
        ],
    )

    payload = ExplorerApiOutput.from_internal(
        internal, filter_tags=lambda values: values
    ).model_dump(by_alias=True)

    assert payload["places"][0]["sourcePlaces"][0]["evidenceType"] == "raw_prompt"


def test_api_budget_is_always_total_trip_per_person() -> None:
    internal = ExplorerOutput(
        status="ready",
        intakeId="intake-group-budget",
        input_ADM="Hà Nội",
        people={"adults": 3, "children": 0, "infants": 0},
        budget=ExplorerBudget(
            level="medium",
            targetAmount=7_500_001,
            currency="VND",
            source="raw_prompt",
            basis="group_total",
        ),
    )

    payload = ExplorerApiOutput.from_internal(
        internal, filter_tags=lambda values: values
    ).model_dump(by_alias=True)

    assert payload["budget"] == {
        "amountPerPerson": 2_500_000,
        "currency": "VND",
        "level": "medium",
    }


def test_api_drops_notes_that_cannot_be_linked_to_a_place() -> None:
    internal = ExplorerOutput(
        status="ready",
        intakeId="intake-unlinked-note",
        input_ADM="Huế",
        places=[
            ExplorerPlace(
                name="Đại Nội Huế",
                confidence=0.95,
                sourcePlaces=[
                    PlaceSource(
                        origin="input",
                        evidenceType="raw_prompt",
                        evidence="tham quan Đại Nội Huế",
                    )
                ],
            )
        ],
        urlNotes=[SourceNote(summary="Nên mang theo nước", evidenceType="raw_prompt")],
    )

    payload = ExplorerApiOutput.from_internal(
        internal, filter_tags=lambda values: values
    ).model_dump(by_alias=True)

    assert "urlNotes" not in payload
    assert payload["places"][0]["sourcePlaces"][0]["urlNotes"] == []


def test_api_preferences_and_avoids_only_use_tags_auto_keys(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "địa phương: [local food]\n"
        "đồ uống: [coffee]\n"
        "nightlife: [nightlife]\n",
        encoding="utf-8",
    )
    catalog = YamlTagCatalog(path)
    internal = ExplorerOutput(
        status="ready",
        intakeId="intake-tags",
        input_ADM="Đà Nẵng",
        shortPreferences=["địa phương", "đồ uống", "unknown_preference"],
        shortAvoids=["nightlife", "crowded_places"],
    )

    payload = ExplorerApiOutput.from_internal(
        internal, filter_tags=catalog.filter_allowed
    ).model_dump(by_alias=True)

    assert payload["shortPreferences"] == ["địa phương", "đồ uống"]
    assert payload["shortAvoids"] == ["nightlife"]
