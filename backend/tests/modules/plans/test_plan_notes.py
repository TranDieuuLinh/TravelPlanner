from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.domain.plan_notes import (
    compose_plan_source_note,
    source_note_provenance,
)


def test_composes_one_display_note_from_short_normalized_sources() -> None:
    note = compose_plan_source_note(
        source_activity="gọi cà phê trứng",
        source_evidence={
            "stt": "Video khuyên đến vào buổi sáng",
            "ocr": "CÀ PHÊ GIẢNG",
        },
        provider_description="Quán cà phê lâu đời gần khu phố cổ",
    )

    assert note == (
        "Gọi cà phê trứng. Video khuyên đến vào buổi sáng. "
        "CÀ PHÊ GIẢNG. Quán cà phê lâu đời gần khu phố cổ."
    )


def test_plan_item_serializes_note_source_provenance_in_revision_json() -> None:
    sources = source_note_provenance(
        source_refs=["https://example.com/reel"],
        evidence_types=["stt", "ocr", "stt"],
        provider="google_maps_scraper",
        provider_ref="google-place-id",
        provider_fetched_at="2026-08-05T09:00:00+00:00",
        include_provider=True,
    )
    item = PlanItem(
        name="Cà phê Giảng",
        timeWindow="08:00-09:00",
        placeType="selected_place",
        timelineCategory="activity",
        source="selected_place",
        notes="Gọi cà phê trứng vào buổi sáng.",
        noteSources=sources,
        personalNotes="Gọi ít đường.",
    )

    payload = item.model_dump(mode="json", by_alias=True)

    assert payload["notes"] == "Gọi cà phê trứng vào buổi sáng."
    assert payload["personalNotes"] == "Gọi ít đường."
    assert payload["noteSources"] == [
        {
            "type": "url",
            "ref": "https://example.com/reel",
            "evidenceTypes": ["stt", "ocr"],
            "fetchedAt": None,
        },
        {
            "type": "google_maps",
            "ref": "google-place-id",
            "evidenceTypes": [],
            "fetchedAt": "2026-08-05T09:00:00Z",
        },
    ]


def test_legacy_plan_item_without_note_sources_remains_valid() -> None:
    item = PlanItem.model_validate(
        {
            "name": "Cà phê Giảng",
            "timeWindow": "08:00-09:00",
            "placeType": "selected_place",
            "timelineCategory": "activity",
            "source": "selected_place",
            "notes": "Gọi cà phê trứng.",
            "sourceRefs": ["https://example.com/reel"],
        }
    )

    assert item.note_sources == []
