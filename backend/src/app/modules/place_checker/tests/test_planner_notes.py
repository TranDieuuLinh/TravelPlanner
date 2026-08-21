import asyncio

from app.modules.place_checker.contract import (
    PlaceCheckerInput,
    SourcePlaceEvidence,
    UrlNote,
)
from app.modules.place_checker.enums import EvidenceOrigin
from app.modules.place_checker.planning.builder import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline
from app.shared.contracts.source_note import SourceNote


def _planner_place(result, place_id):
    output = PlaceCheckerPlannerOutputBuilder().build(
        result, start_date="2026-08-20", timezone="Asia/Ho_Chi_Minh"
    )
    return next(place for place in output.places if place.place_id == place_id)


def test_url_note_overrides_google_provider_note() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-url-note"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "provider_note": SourceNote(
                text="Google description",
                source_type="google_maps",
                source_url="https://google.com/maps/place/example",
            ),
            "provenance": first.provenance.model_copy(
                update={
                    "url_notes": [
                        UrlNote(
                            summary="User asks to arrive after breakfast",
                            place_name=first.canonical_name,
                            evidence_type="raw_prompt",
                        ),
                        UrlNote(
                            summary="Creator recommends arriving early",
                            place_name=first.canonical_name,
                            evidence_type="creator_tip",
                            source_url="https://example.test/video",
                        ),
                    ]
                }
            ),
        }
    )

    selected = _planner_place(result, first.place_id)

    assert selected.notes is not None
    assert selected.notes.text == "Creator recommends arriving early"
    assert selected.notes.source_type == "url"
    assert selected.notes.source_url == "https://example.test/video"
    assert selected.personal_notes == "User asks to arrive after breakfast"


def test_raw_prompt_note_becomes_personal_note_without_overriding_provider() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-user-note"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "provider_note": SourceNote(
                text="Google description",
                source_type="google_maps",
                source_url="https://google.com/maps/place/example",
            ),
            "provenance": first.provenance.model_copy(
                update={
                    "url_notes": [
                        UrlNote(
                            summary="Người dùng muốn đến sau bữa sáng.",
                            place_name=first.canonical_name,
                            evidence_type="raw_prompt",
                        )
                    ]
                }
            ),
        }
    )

    selected = _planner_place(result, first.place_id)

    assert selected.notes is not None
    assert selected.notes.text == "Google description"
    assert selected.notes.source_type == "google_maps"
    assert selected.personal_notes == "Người dùng muốn đến sau bữa sáng."


def test_compact_raw_prompt_and_url_notes_reach_planner_with_url_priority() -> None:
    compact = payload().model_dump(mode="json", by_alias=True)
    compact["places"] = [
        {
            "name": "Ho Chi Minh Mausoleum",
            "sourcePlaces": [
                {
                    "evidenceType": "raw_prompt",
                    "sourceUrl": None,
                    "sourceTimeHint": None,
                    "addressHint": None,
                    "urlNotes": [{"summary": "Người dùng muốn ghé sau bữa sáng."}],
                },
                {
                    "evidenceType": "url",
                    "sourceUrl": "https://example.test/hanoi-guide",
                    "sourceTimeHint": "00:42",
                    "addressHint": None,
                    "urlNotes": [{"summary": "Nguồn URL khuyên đến trước 9 giờ."}],
                },
            ],
            "latitude": None,
            "longitude": None,
        }
    ]
    checked_input = PlaceCheckerInput.model_validate(compact)

    result = asyncio.run(
        pipeline().check(checked_input, request_id="request-compact-note-flow")
    )
    first = next(
        place for place in result.checked_places if place.place_id == "kg:mausoleum"
    )
    selected = _planner_place(result, first.place_id)

    assert [note.evidence_type for note in first.provenance.url_notes] == [
        "raw_prompt",
        "url",
    ]
    assert selected.notes is not None
    assert selected.notes.text == "Nguồn URL khuyên đến trước 9 giờ."
    assert selected.notes.source_type == "url"
    assert selected.notes.source_url == "https://example.test/hanoi-guide"
    assert selected.personal_notes == "Người dùng muốn ghé sau bữa sáng."


def test_google_provider_note_is_used_without_url_note() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-google-note"))
    first = result.checked_places[0]
    google_note = SourceNote(
        text="Google description",
        source_type="google_maps",
        source_url="https://google.com/maps/place/example",
    )
    result.checked_places[0] = first.model_copy(update={"provider_note": google_note})

    selected = _planner_place(result, first.place_id)

    assert selected.notes == google_note


def test_tiktok_source_evidence_survives_when_url_note_is_unattached() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-tiktok-source")
    )
    first = result.checked_places[0]
    tiktok_source = SourcePlaceEvidence(
        origin=EvidenceOrigin.url,
        evidence_type="transcript",
        evidence="8h30: Đi dạo Phố đi bộ Hồ Gươm",
        source_url="https://www.tiktok.com/@creator/video/1",
    )
    result.checked_places[0] = first.model_copy(
        update={
            "provider_note": SourceNote(
                text="Google description",
                source_type="google_maps",
                source_url="https://google.com/maps/place/example",
            ),
            "provenance": first.provenance.model_copy(
                update={
                    "source_places": [tiktok_source],
                    "url_notes": [],
                }
            ),
        }
    )

    selected = _planner_place(result, first.place_id)

    assert selected.notes is not None
    assert selected.notes.text == "8h30: Đi dạo Phố đi bộ Hồ Gươm"
    assert selected.notes.source_type == "url"
    assert selected.notes.source_url == tiktok_source.source_url
