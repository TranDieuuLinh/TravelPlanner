from __future__ import annotations

import json

from pydantic import ValidationError

from app.core.config import settings
from app.integrations.llm.base import LLMClient
from app.modules.plans.dto.agent_contracts import (
    BudgetCalculationBasis,
    BudgetInputMode,
)
from app.modules.plans.explorer.schema import ExploreResponse, FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelExtractionResult


class ExploreResponseFormatter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def format(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[UrlReelExtractionResult] | None = None,
    ) -> ExploreResponse:
        if not settings.enable_llm_explore_formatter:
            raise RuntimeError("ENABLE_LLM_EXPLORE_FORMATTER must be true for /api/plans/explore/full.")
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for /api/plans/explore/full.")

        url_results = url_reel_results or []
        transcript = "\n\n".join(result.speech_to_text.text for result in url_results if result.speech_to_text.text)
        image_ocr_text = "\n\n".join(
            image.ocr_text
            for image in payload.image_contexts
            if image.status == "ok" and image.ocr_text
        )

        system_prompt = (
            "You are the Explorer formatter for a travel planning backend. "
            "Return only valid JSON matching the required ExploreResponse schema. "
            "Read the request, URL metadata, STT transcripts, and OCR text from uploaded screenshots/images, then fill the JSON as completely as the evidence allows. "
            "Use rawRequest as the source of user intent. Use transcripts, OCR text, and metadata as evidence for places, interests, and constraints. "
            "Use request.userState.travelStyle as the user's explicit travel style and preserve it in intent.travelStyle unless stronger user input says otherwise. "
            "Put restaurants, dishes, and coffee shops only in foodPlaces; classify them as food or cafe. "
            "Put sightseeing, entertainment, hotels, transport, free-time, and unclear locations only in placeCandidates; never duplicate an item across the two arrays. "
            "For every place item, set category to exactly one of attraction, food, cafe, hotel, transport, free_time, or other. "
            "Normalize cheap, low, budget, economical, student, or tiet kiem budget language to intent.budgetLevel=budget; medium, mid, balanced, reasonable, or trung binh to medium; and high, comfortable, or thoai mai to high. "
            "Set tripSpec.budget.inputMode to qualitative when the user gives only a spending level, exact when the user gives one target amount, range when the user gives a minimum and maximum, and unknown when budget is absent. "
            "For 'under' or 'maximum' amounts, set isHardCap=true and put the limit in maxAmount. For approximate amounts, use targetAmount and isHardCap=false. "
            "Keep minAmount <= targetAmount <= maxAmount, use a three-letter uppercase currency code, and fill calculationBasis from destination, party size, days, nights, and budgetLevel when those values are known. "
            "Do not invent minAmount, targetAmount, or maxAmount for a qualitative budget unless reliable price evidence is present in the request or supplied context; leave them null and explain the missing estimate in notes. "
            "Do not invent exact place names, addresses, prices, opening hours, or logistics unless clearly supported by the request, transcript, OCR text, metadata, or destination. "
            "If information is missing, leave optional fields null/empty and add concise missingInfoQuestions."
        )
        user_payload = json.dumps(
            {
                "requiredOutputShape": ExploreResponse.model_json_schema(),
                "request": payload.model_dump(mode="json", by_alias=True),
                "transcript": transcript,
                "imageOcrText": image_ocr_text,
                "urlReelResults": [result.model_dump(mode="json", by_alias=True) for result in url_results],
                "imageContexts": [
                    image.model_dump(mode="json", by_alias=True)
                    for image in payload.image_contexts
                ],
            },
            ensure_ascii=False,
        )

        try:
            raw = await self.llm.generate_json(system_prompt=system_prompt, user_payload=user_payload)
            return _complete_budget_basis(ExploreResponse.model_validate_json(raw))
        except (RuntimeError, ValidationError, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError("Gemini failed to generate a valid ExploreResponse JSON.") from exc


def _complete_budget_basis(response: ExploreResponse) -> ExploreResponse:
    budget = response.trip_spec.budget
    has_budget = budget.input_mode != BudgetInputMode.unknown or any(
        amount is not None
        for amount in (budget.min_amount, budget.target_amount, budget.max_amount)
    )
    if not has_budget:
        return response

    budget.calculation_basis = BudgetCalculationBasis(
        partySize=response.trip_spec.party_size,
        days=response.trip_spec.days,
        nights=max(response.trip_spec.days - 1, 0),
        destination=response.intent.destination,
        priceTier=response.intent.budget_level,
    )
    return response
