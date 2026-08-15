import asyncio

from app.modules.place_checker.contract import UrlNote
from app.modules.place_checker.planning_output import PlaceCheckerPlannerOutputBuilder
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
                            summary="Creator recommends arriving early",
                            place_name=first.canonical_name,
                            evidence_type="creator_tip",
                            source_url="https://example.test/video",
                        )
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
