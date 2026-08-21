import asyncio
import json

import pytest

from app.modules.place_checker.adapters.gemini_source_note_translator import (
    GeminiSourceNoteTranslator,
)
from app.modules.place_checker.contract import UrlNote
from app.modules.place_checker.localization.contract import (
    SourceNoteTranslationRequest,
)
from app.modules.place_checker.localization.service import (
    SourceNoteLocalizationService,
    is_probably_vietnamese,
)
from app.modules.place_checker.planning.builder import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline
from app.shared.contracts.source_note import SourceNote


def _result_with_provider_note(source_type: str = "google_maps"):
    result = asyncio.run(pipeline().check(payload(), request_id="localization-test"))
    first = result.checked_places[0]
    updated = first.model_copy(
        update={
            "provider_note": SourceNote(
                text=(
                    "Grand plaza where Ho Chi Minh declared Vietnam's "
                    "independence from France and where his body now lies."
                ),
                source_type=source_type,
                source_url="https://google.com/maps/place/ba-dinh",
            )
        }
    )
    return result.model_copy(
        update={"checked_places": [updated, *result.checked_places[1:]]}
    )


class RecordingTranslator:
    def __init__(self) -> None:
        self.calls: list[list[SourceNoteTranslationRequest]] = []

    async def translate_many(self, requests):
        self.calls.append(requests)
        return {
            request.request_id: (
                "Quảng trường lớn nơi Chủ tịch Hồ Chí Minh đọc Tuyên ngôn "
                "Độc lập; Lăng Chủ tịch Hồ Chí Minh nằm trong khu vực này."
            )
            for request in requests
        }


@pytest.mark.parametrize("source_type", ["google_maps", "knowledge_graph"])
def test_localizes_selected_provider_note_and_preserves_source(source_type) -> None:
    translator = RecordingTranslator()
    service = SourceNoteLocalizationService(translator)

    localized = asyncio.run(service.localize(_result_with_provider_note(source_type)))
    note = localized.checked_places[0].provider_note

    assert note is not None
    assert note.text.startswith("Quảng trường lớn nơi Chủ tịch Hồ Chí Minh")
    assert note.source_type == source_type
    assert note.source_url == "https://google.com/maps/place/ba-dinh"
    assert len(translator.calls) == 1


def test_omits_untranslated_provider_note_when_translator_is_unavailable() -> None:
    original = _result_with_provider_note()
    localized = asyncio.run(SourceNoteLocalizationService().localize(original))

    assert localized.checked_places[0].provider_note is None
    assert original.checked_places[0].provider_note is not None
    assert any("chưa thể Việt hóa" in warning for warning in localized.warnings)
    assert localized.metadata.partial is True


def test_url_note_priority_avoids_unused_provider_translation() -> None:
    result = _result_with_provider_note()
    first = result.checked_places[0]
    first = first.model_copy(
        update={
            "provenance": first.provenance.model_copy(
                update={
                    "url_notes": [
                        UrlNote(
                            summary="Nguồn URL khuyên đến vào buổi sáng.",
                            place_name=first.canonical_name,
                            evidence_type="creator_tip",
                            source_url="https://example.test/video",
                        )
                    ]
                }
            )
        }
    )
    result = result.model_copy(
        update={"checked_places": [first, *result.checked_places[1:]]}
    )
    translator = RecordingTranslator()

    localized = asyncio.run(SourceNoteLocalizationService(translator).localize(result))
    compact = PlaceCheckerPlannerOutputBuilder().build(
        localized,
        start_date="2026-08-21",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert translator.calls == []
    assert compact.places[0].notes.text == "Nguồn URL khuyên đến vào buổi sáng."


def test_translation_cache_avoids_a_repeated_provider_call() -> None:
    translator = RecordingTranslator()
    service = SourceNoteLocalizationService(translator)

    asyncio.run(service.localize(_result_with_provider_note()))
    localized = asyncio.run(service.localize(_result_with_provider_note()))

    assert len(translator.calls) == 1
    assert localized.checked_places[0].provider_note is not None


def test_pipeline_localizes_provider_note_before_returning_result() -> None:
    checker = pipeline()
    repository = checker.evidence_enrichment.metadata_repository
    original_metadata = repository.data["kg:mausoleum"]
    repository.data["kg:mausoleum"] = original_metadata.model_copy(
        update={
            "source_note": SourceNote(
                text="Historic square in Hanoi where independence was declared.",
                source_type="knowledge_graph",
            )
        }
    )
    checker.source_note_localization = SourceNoteLocalizationService(
        RecordingTranslator()
    )

    result = asyncio.run(
        checker.check(payload(), request_id="pipeline-localization-test")
    )

    assert result.checked_places[0].provider_note is not None
    assert result.checked_places[0].provider_note.text.startswith("Quảng trường lớn")
    assert "source_note_localization" in result.metadata.phase_duration_ms


def test_language_guard_rejects_english_even_with_a_vietnamese_name() -> None:
    assert not is_probably_vietnamese(
        "Grand plaza where Hồ Chí Minh declared Vietnam's independence."
    )
    assert is_probably_vietnamese(
        "Quảng trường nơi Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập."
    )


def test_gemini_translator_uses_structured_batch_contract() -> None:
    class Client:
        call = None

        async def generate(self, user_prompt, **kwargs):
            self.call = (user_prompt, kwargs)
            request_id = json.loads(user_prompt)["notes"][0]["requestId"]
            return json.dumps(
                {
                    "translations": [
                        {
                            "requestId": request_id,
                            "text": "Quảng trường lịch sử tại Hà Nội.",
                        }
                    ]
                },
                ensure_ascii=False,
            )

    client = Client()
    request = SourceNoteTranslationRequest(
        request_id="note-1",
        place_name="Ba Dinh Square",
        text="Historic square in Hanoi.",
    )

    translated = asyncio.run(
        GeminiSourceNoteTranslator(client).translate_many([request])
    )

    assert translated == {"note-1": "Quảng trường lịch sử tại Hà Nội."}
    assert "Giữ nguyên tên riêng" in client.call[1]["system_prompt"]
    assert client.call[1]["temperature"] == 0.0
    assert client.call[1]["response_json_schema"]["properties"]["translations"]


def test_gemini_translator_rejects_incomplete_batch() -> None:
    class Client:
        async def generate(self, user_prompt, **kwargs):
            return '{"translations": []}'

    request = SourceNoteTranslationRequest(
        request_id="note-1",
        place_name="Ba Dinh Square",
        text="Historic square in Hanoi.",
    )

    with pytest.raises(ValueError, match="every requested note"):
        asyncio.run(GeminiSourceNoteTranslator(Client()).translate_many([request]))
