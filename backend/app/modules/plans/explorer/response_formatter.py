from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.core.config import settings
from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.constraint_policy import (
    ConstraintPolicy,
    GeographicScopePolicy,
    GeographicScopeType,
    normalize_constraint_value,
)
from app.modules.plans.dto.agent_contracts import (
    BudgetCalculationBasis,
    BudgetInputMode,
)
from app.modules.plans.explorer.schema import ExploreBundleDraft, FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelExtractionResult


class ExploreResponseFormatter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def format(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[UrlReelExtractionResult] | None = None,
    ) -> ExploreBundleDraft:
        if not settings.enable_llm_explore_formatter:
            raise RuntimeError("ENABLE_LLM_EXPLORE_FORMATTER must be true for /api/plans/explore/full.")
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for /api/plans/explore/full.")

        url_results = url_reel_results or []
        transcript = "\n\n".join(result.speech_to_text.text for result in url_results if result.speech_to_text.text)
        reel_visual_text = "\n\n".join(
            result.frame_vision.text
            for result in url_results
            if result.frame_vision.status == "ok" and result.frame_vision.text
        )
        image_ocr_text = "\n\n".join(
            image.ocr_text
            for image in payload.image_contexts
            if image.status == "ok" and image.ocr_text
        )

        system_prompt = (
            "You are the Explorer formatter for a travel planning backend. "
            "Return only valid JSON matching the required ExploreBundleDraft schema. "
            "Read the request, URL metadata, STT transcripts, and OCR text from uploaded screenshots/images, then fill the JSON as completely as the evidence allows. "
            "Use rawRequest as the source of user intent. Use transcripts, OCR text, and metadata as evidence for places, interests, and constraints. "
            "Use request.userState.travelStyle as the user's explicit travel style and preserve it in intent.travelStyle unless stronger user input says otherwise. "
            "Use request.userState.preferenceProfile as long-term context, but let explicit rawRequest constraints override it for this trip. "
            "The explorer object must contain only intent, tripSpec, assumptions, missingInfoQuestions, and preferenceSnapshot. Never include places, URL results, transcripts, OCR text, or debug data in explorer. "
            "Normalize hard exclusions into intent.constraintPolicy. Use excludedPlaceTypes for categories the user rejects, for example cemetery when the user says they do not want cemeteries. Use geographicScope.type=coastal when the user restricts the trip to coastal areas. Keep the original concise wording in intent.constraints for explanation. Use avoidPlaces only for specifically named places, not generic categories. "
            "Also produce explorer.preferenceSnapshot.signals for short-term preferences evidenced by this intake. Each signal needs dimension, normalized value, score from -1 to 1, confidence, scope, destination, and sourceTypes. Never copy raw prompt, OCR, transcript, or evidence excerpts into preference signals. "
            "Put concrete places from rawRequest and image OCR in places.placeCandidates. URL place extraction is already normalized by the URL adapter and will be merged after this formatter, so use URL results for intent/interests/constraints but do not copy URL places into places.placeCandidates. "
            "Do not create separate foodPlaces or urlReelSignals arrays. "
            "For every candidate, set category to exactly one of attraction, food, cafe, hotel, transport, free_time, nature, culture, shopping, nightlife, wellness, adventure, beach, family, cemetery, or other. "
            "Add normalized candidate attributes when supported, such as local, hidden_gem, photogenic, quiet, crowded, budget, premium, family_friendly, outdoor, coastal, late_night, romantic, or accessible. Use coastal only when the evidence supports a coastal location; do not infer it merely from the trip-wide constraint. "
            "Every candidate produced here must preserve its evidence source: use user_prompt for a place from rawRequest and ocr for a place from image OCR. Set source URL to null. "
            "Set preferenceLevel=preferred for an automatically extracted place. Use must_visit only when rawRequest explicitly says the place is mandatory; never infer must_visit from a Reel mention alone. "
            "If the same place appears in multiple inputs, return one candidate with all sources. "
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
                "requiredOutputShape": ExploreBundleDraft.model_json_schema(),
                "request": payload.model_dump(mode="json", by_alias=True),
                "transcript": transcript,
                "imageOcrText": image_ocr_text,
                "reelFrameVisionText": reel_visual_text,
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
            response = ExploreBundleDraft.model_validate_json(raw)
            response = _complete_constraint_policy(response, payload.raw_request)
            return _complete_budget_basis(response)
        except (RuntimeError, ValidationError, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError(
                "Gemini failed to generate a valid ExploreBundleDraft JSON."
            ) from exc


def _complete_budget_basis(response: ExploreBundleDraft) -> ExploreBundleDraft:
    budget = response.explorer.trip_spec.budget
    has_budget = budget.input_mode != BudgetInputMode.unknown or any(
        amount is not None
        for amount in (budget.min_amount, budget.target_amount, budget.max_amount)
    )
    if not has_budget:
        return response

    budget.calculation_basis = BudgetCalculationBasis(
        partySize=response.explorer.trip_spec.party_size,
        days=response.explorer.trip_spec.days,
        nights=max(response.explorer.trip_spec.days - 1, 0),
        destination=response.explorer.intent.destination,
        priceTier=response.explorer.intent.budget_level,
    )
    return response


def _complete_constraint_policy(
    response: ExploreBundleDraft,
    raw_request: str,
) -> ExploreBundleDraft:
    normalized_request = normalize_constraint_value(raw_request).replace("_", " ")
    policy = response.explorer.intent.constraint_policy.model_copy(deep=True)
    excluded_types = list(policy.excluded_place_types)

    cemetery_exclusion_patterns = (
        r"\bkhong(?: muon| thich)?(?: di| den| ghe)?(?: cac)? nghia trang\b",
        r"\btranh(?: cac)? nghia trang\b",
        r"\b(?:do not|don't|avoid|dislike)(?: visit(?:ing)?| go(?:ing)? to)? cemeter(?:y|ies)\b",
        r"\bavoid graveyards?\b",
    )
    if any(
        re.search(pattern, normalized_request)
        for pattern in cemetery_exclusion_patterns
    ):
        excluded_types.append("cemetery")

    coastal_only_patterns = (
        r"\bchi(?: di| o| tham quan| chon)?(?: khu vuc)? ven bien\b",
        r"\bchi(?: di| o| tham quan| chon)?(?: khu vuc)? bo bien\b",
        r"\b(?:coastal|coast|seaside) only\b",
        r"\bonly(?: visit| stay in| choose)?(?: the)? coastal\b",
    )
    geographic_scope = policy.geographic_scope
    if any(
        re.search(pattern, normalized_request)
        for pattern in coastal_only_patterns
    ):
        geographic_scope = GeographicScopePolicy(
            type=GeographicScopeType.coastal
        )

    completed_policy = ConstraintPolicy(
        excludedPlaceTypes=excluded_types,
        geographicScope=geographic_scope,
    )
    intent = response.explorer.intent.model_copy(
        update={"constraint_policy": completed_policy}
    )
    explorer = response.explorer.model_copy(update={"intent": intent})
    return response.model_copy(update={"explorer": explorer})
