from __future__ import annotations

import asyncio
import json

from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedPlace,
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)


class RecordingLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_payload = ""
        self.response_schema: dict = {}

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        self.system_prompt = system_prompt
        self.user_payload = user_payload
        return json.dumps(
            {
                "explorer": {
                    "intent": {"destination": "Hà Nội"},
                    "tripSpec": {"days": 1},
                },
                "places": {
                    "placeCandidates": [
                        {
                            "name": "Xôi Yến",
                            "category": "food",
                            "sources": [
                                {
                                    "type": "url",
                                    "url": "https://example.com/reel",
                                }
                            ],
                            "confidence": 0.95,
                            "priority": 1,
                            "sourceOrder": 1,
                            "sourceTimeHint": "breakfast",
                            "sourceActivity": "Order turmeric sticky rice.",
                        }
                    ]
                },
            }
        )

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        self.system_prompt = system_prompt
        self.user_payload = user_payload
        self.response_schema = response_schema
        return json.dumps(
            {
                "intent": {
                    "destination": "Hà Nội",
                    "interests": ["food", "culture"],
                },
                "tripSpec": {"days": 3},
                "assumptions": [],
                "missingInfoQuestions": [],
                "preferenceSnapshot": {"signals": []},
            }
        )


def test_url_context_formatter_sends_compact_summary_and_structured_schema(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.plans.explorer.response_formatter.settings.enable_llm_explore_formatter",
        True,
    )
    monkeypatch.setattr(
        "app.modules.plans.explorer.response_formatter.settings.gemini_api_key",
        "test-key",
    )
    llm = RecordingLLM()
    formatter = ExploreResponseFormatter(llm)  # type: ignore[arg-type]
    url = "https://example.com/reel"
    result = UrlReelExtractionResult(
        url=url,
        platform="tiktok",
        metadata=UrlMetadata(
            originalUrl=url,
            canonicalUrl=url,
            platform="tiktok",
            title="A perfect day in Hanoi",
            raw={"cookies": "must-not-leak", "formats": [{"url": "signed"}]},
        ),
        artifacts=MediaArtifacts(),
        speechToText=SpeechToTextResult(
            text="First, have breakfast at Xôi Yến.",
            durationSeconds=1,
        ),
        frameVision=FrameVisionResult(text="Frame 1: Xôi Yến", status="ok"),
        extractedContext=ExtractedContext(
            extractedPlaces=["Xôi Yến"],
            extractedPlaceDetails=[
                ExtractedPlace(
                    name="Xôi Yến",
                    category="food",
                    sourceOrder=1,
                    sourceTimeHint="breakfast",
                    sourceActivity="Order turmeric sticky rice.",
                )
            ],
            interests=["food", "culture"],
            confidence=0.9,
        ),
        timings={},
    )

    response = asyncio.run(
        formatter.format_context(
            FullExploreRequest(
                rawRequest="Follow this URL closely.",
                destination="Hà Nội",
                urls=[url],
            ),
            url_reel_results=[result],
        )
    )

    assert "untrusted evidence" in llm.system_prompt
    assert "Do not produce places" in llm.system_prompt
    sent = json.loads(llm.user_payload)
    assert "requiredOutputShape" not in sent
    assert "transcript" not in sent
    assert "reelFrameVisionText" not in sent
    assert "urlReelResults" not in sent
    assert sent["urlSummaries"][0]["stopCount"] == 1
    assert sent["urlSummaries"][0]["categoryCounts"] == {"food": 1}
    assert sent["urlSummaries"][0]["activities"] == [
        "Order turmeric sticky rice."
    ]
    assert "must-not-leak" not in llm.user_payload
    assert "places" not in llm.response_schema["properties"]
    assert response.intent.destination == "Hà Nội"
    assert response.trip_spec.days == 3
