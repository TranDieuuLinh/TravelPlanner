import asyncio
import json

from app.modules.explorer.adapters.gemini import GeminiExplorerDraftGenerator
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult


class ActivityNoteClient:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.user_prompt = user_prompt
        self.system_prompt = kwargs["system_prompt"]
        return json.dumps({
            "urlNotes": [{
                "summary": "Explore cafés, shops, and the night market.",
                "placeName": "Old Quarter",
                "evidenceType": "frame_ocr",
                "sourceUrl": "https://example.com/reel",
            }]
        })


class PlaceNameClient:
    def __init__(self) -> None:
        self.system_prompt = ""

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.system_prompt = kwargs["system_prompt"]
        return json.dumps({
            "places": [{
                "name": "Lăng Chủ tịch Hồ Chí Minh",
                "confidence": 0.9,
                "sourcePlaces": [{
                    "origin": "input",
                    "evidenceType": "raw_prompt",
                    "evidence": "ghé lăng bác",
                }],
            }]
        })


def test_prompt_requests_semantic_place_name_normalization_in_name_only() -> None:
    client = PlaceNameClient()
    generator = GeminiExplorerDraftGenerator(client)  # type: ignore[arg-type]

    draft = asyncio.run(generator.from_prompt("Tôi muốn ghé lăng bác"))

    assert draft.places[0].name == "Lăng Chủ tịch Hồ Chí Minh"
    assert "place-name expert" in client.system_prompt
    assert "name normalization, not verification" in client.system_prompt
    assert "Return the normalized value only in places[].name" in client.system_prompt
    assert set(draft.places[0].model_dump(by_alias=True)) == {
        "name", "addressHint", "confidence", "sourcePlaces"
    }


def test_source_prompt_keeps_supported_activities_as_url_notes() -> None:
    client = ActivityNoteClient()
    generator = GeminiExplorerDraftGenerator(client)  # type: ignore[arg-type]
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/reel",
        status="succeeded",
        artifacts=[SourceArtifact(
            artifactType="frame_ocr",
            text=(
                "Explore the Old Quarter: there are many cute cafés, shops "
                "and a night market"
            ),
            sourceUrl="https://example.com/reel",
        )],
    )

    draft = asyncio.run(generator.from_sources(raw_prompt=None, sources=[source]))

    assert draft.url_notes[0].place_name == "Old Quarter"
    assert "night market" in draft.url_notes[0].summary
    assert "activities available there" in client.system_prompt
    assert "urlNotesIncludeActivitiesAndFunFacts" in client.user_prompt
