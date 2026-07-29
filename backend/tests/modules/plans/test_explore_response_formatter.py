from __future__ import annotations

import asyncio
import json

from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
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


def test_formatter_prioritizes_url_itinerary_and_excludes_raw_provider_payload(
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
        extractedContext=ExtractedContext(),
        timings={},
    )

    response = asyncio.run(
        formatter.format(
            FullExploreRequest(
                rawRequest="Follow this URL closely.",
                destination="Hà Nội",
                urls=[url],
            ),
            url_reel_results=[result],
        )
    )

    assert "primary planning blueprint" in llm.system_prompt
    assert "untrusted evidence" in llm.system_prompt
    assert "established Vietnamese place name" in llm.system_prompt
    sent = json.loads(llm.user_payload)
    assert "raw" not in sent["urlReelResults"][0]["metadata"]
    assert "must-not-leak" not in llm.user_payload
    candidate = response.places.place_candidates[0]
    assert candidate.source_order == 1
    assert candidate.source_day == 1
    assert candidate.source_time_hint == "breakfast"
    assert candidate.sources[0].url == url
