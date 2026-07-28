from __future__ import annotations

import json

from pydantic import ValidationError

from app.core.config import settings
from app.integrations.llm.base import LLMClient
from app.modules.plans.explorer.schema import ExploreResponse, FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelInput
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService


class ExploreResponseFormatter:
    def __init__(
        self,
        llm: LLMClient,
        url_reels: UrlReelExtractionService | None = None,
    ) -> None:
        self.llm = llm
        self.url_reels = url_reels or UrlReelExtractionService()

    async def format(self, payload: FullExploreRequest) -> ExploreResponse:
        if not settings.enable_llm_explore_formatter:
            raise RuntimeError("ENABLE_LLM_EXPLORE_FORMATTER must be true for /api/plans/explore/full.")
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for /api/plans/explore/full.")

        url_results = [
            self.url_reels.extract(UrlReelInput(url=url, destination=payload.destination))
            for url in payload.urls
        ]
        transcript = "\n\n".join(result.speech_to_text.text for result in url_results if result.speech_to_text.text)

        system_prompt = (
            "You are the Explorer formatter for a travel planning backend. "
            "Return only valid JSON matching the required ExploreResponse schema. "
            "Read the request, URL metadata, and STT transcripts, then fill the JSON as completely as the evidence allows. "
            "Use rawRequest as the source of user intent. Use transcripts and metadata as evidence for places, interests, and constraints. "
            "Do not invent exact place names, addresses, prices, opening hours, or logistics unless clearly supported by the request, transcript, metadata, or destination. "
            "If information is missing, leave optional fields null/empty and add concise missingInfoQuestions. "
            "Always include debug.transcript, debug.rawExtractedText, and debug.urlStatuses."
        )
        user_payload = json.dumps(
            {
                "requiredOutputShape": ExploreResponse.model_json_schema(),
                "request": payload.model_dump(mode="json", by_alias=True),
                "transcript": transcript,
                "urlReelResults": [result.model_dump(mode="json", by_alias=True) for result in url_results],
                "debugDefaults": {
                    "transcript": transcript or None,
                    "rawExtractedText": transcript or None,
                    "urlStatuses": [
                        {
                            "url": result.url,
                            "platform": result.platform,
                            "needsImageUpload": result.needs_image_upload,
                            "speechToText": result.speech_to_text.model_dump(mode="json", by_alias=True),
                            "timings": result.timings,
                        }
                        for result in url_results
                    ],
                },
            },
            ensure_ascii=False,
        )

        try:
            raw = await self.llm.generate_json(system_prompt=system_prompt, user_payload=user_payload)
            return ExploreResponse.model_validate_json(raw)
        except (RuntimeError, ValidationError, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError("Gemini failed to generate a valid ExploreResponse JSON.") from exc
