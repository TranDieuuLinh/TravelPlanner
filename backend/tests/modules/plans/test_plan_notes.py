from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.domain.plan_notes import (
    PlanNoteSource,
    compose_plan_source_note,
    compose_video_place_note,
    merge_note_sources,
    source_note_provenance,
)
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.place_selector.skeleton_builder import DayBlock


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
        video_note="Video tham khảo có nhắc đến Cà phê Giảng.",
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
                "text": "Video tham khảo có nhắc đến Cà phê Giảng.",
                "evidence": None,
            "ref": "https://example.com/reel",
            "evidenceTypes": ["stt", "ocr"],
            "fetchedAt": None,
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


def test_source_notes_are_place_scoped_and_vietnamese() -> None:
    assert compose_video_place_note(
        place_name="Hoàng thành Thăng Long",
        source_activity="Explore Hoàng thành Thăng Long and wander around the Old Quarter",
    ) is None
    assert compose_video_place_note(
        place_name="Hoàng thành Thăng Long",
        source_activity=(
            "Creator bắt đầu ngày đầu tiên ở cổng Bắc của di sản UNESCO này."
        ),
        source_evidence={
            "ocr": (
                "Day 1, we started at the UNESCO site, "
                "Imperial Citadel of Thang Long, North Gate"
            )
        },
    ) == "Creator bắt đầu ngày đầu tiên ở cổng Bắc của di sản UNESCO này."
    assert compose_video_place_note(
        place_name="Hoàng thành Thăng Long",
        source_activity="Video tham khảo có nhắc đến Hoàng thành Thăng Long.",
    ) is None
    assert compose_video_place_note(
        place_name="Hoàng thành Thăng Long",
        source_activity="Creator khuyên nên đến đây từ sáng sớm.",
        source_evidence={"stt": "Hoàng thành Thăng Long"},
    ) is None

def test_plan_item_keeps_creator_story_but_drops_provider_note() -> None:
    source_notes = [
        PlanNoteSource(
            type="url",
            text="Video tham khảo có nhắc đến Hoàng thành Thăng Long.",
        ),
        PlanNoteSource(
            type="google_maps",
            text="Theo dữ liệu từ Google, đây là một địa điểm tham quan.",
        ),
    ]
    candidate = SelectablePlace(
        name="Hoàng thành Thăng Long",
        placeType="Historical landmark",
        regionKey="vn,hanoi",
        noteSources=source_notes,
    )

    item = PlaceSelectorService()._build_activity_item(
        candidate,
        DayBlock(
            role="main_experience",
            time_window="09:00-10:30",
            duration_minutes=90,
            activity=True,
        ),
        mode="main",
        selected_source=True,
    )

    assert [source.type for source in item.note_sources] == ["url"]


def test_merge_note_sources_drops_provider_notes() -> None:
    merged = merge_note_sources(
        [
            PlanNoteSource(
                type="url",
                text="Creator gọi cà phê trứng vào buổi sáng.",
            ),
            PlanNoteSource(
                type="google_maps",
                text="Theo dữ liệu từ Google, đây là một quán cà phê.",
            ),
            PlanNoteSource(type="place_provider", text="Provider metadata."),
        ]
    )

    assert [source.type for source in merged] == ["url"]
