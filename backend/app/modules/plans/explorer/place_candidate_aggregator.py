from __future__ import annotations

import re
import unicodedata

from app.modules.plans.dto.agent_contracts import PlaceCandidateHint
from app.modules.plans.explorer.schema import (
    PlaceCandidateSource,
    PlaceCandidateSourceType,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    UrlReelExtractionResult,
)


class PlaceCandidateAggregator:
    def aggregate(
        self,
        *,
        destination: str,
        generated: list[UnifiedPlaceCandidate],
        explicit: list[PlaceCandidateHint],
        url_results: list[UrlReelExtractionResult],
    ) -> list[UnifiedPlaceCandidate]:
        candidates = list(generated)
        candidates.extend(self._from_explicit(explicit))
        candidates.extend(self._from_url_results(url_results))

        destination_key = _dedupe_key(destination)
        merged: dict[str, UnifiedPlaceCandidate] = {}
        order: list[str] = []
        for candidate in candidates:
            key = _dedupe_key(candidate.name)
            if not key or key == destination_key:
                continue
            if key not in merged:
                merged[key] = candidate.model_copy(deep=True)
                order.append(key)
                continue
            merged[key] = _merge(merged[key], candidate)
        return [merged[key] for key in order]

    def _from_explicit(
        self,
        candidates: list[PlaceCandidateHint],
    ) -> list[UnifiedPlaceCandidate]:
        return [
            UnifiedPlaceCandidate(
                name=candidate.name,
                category=candidate.category,
                addressHint=candidate.address,
                sources=[
                    PlaceCandidateSource(
                        type=(
                            PlaceCandidateSourceType.url
                            if candidate.source_url
                            else PlaceCandidateSourceType.user_prompt
                        ),
                        url=candidate.source_url,
                    )
                ],
                confidence=candidate.confidence,
                priority=candidate.priority,
                notes=candidate.notes,
            )
            for candidate in candidates
        ]

    def _from_url_results(
        self,
        results: list[UrlReelExtractionResult],
    ) -> list[UnifiedPlaceCandidate]:
        candidates: list[UnifiedPlaceCandidate] = []
        for result in results:
            details = result.extracted_context.extracted_place_details
            if details:
                for detail in details:
                    candidates.append(
                        UnifiedPlaceCandidate(
                            name=detail.name,
                            category=detail.category,
                            addressHint=detail.address,
                            sources=[
                                PlaceCandidateSource(
                                    type=PlaceCandidateSourceType.url,
                                    url=result.url,
                                )
                            ],
                            confidence=result.extracted_context.confidence,
                            notes=detail.evidence,
                        )
                    )
                continue
            candidates.extend(
                UnifiedPlaceCandidate(
                    name=name,
                    sources=[
                        PlaceCandidateSource(
                            type=PlaceCandidateSourceType.url,
                            url=result.url,
                        )
                    ],
                    confidence=result.extracted_context.confidence,
                )
                for name in result.extracted_context.extracted_places
            )
        return candidates


def _merge(
    current: UnifiedPlaceCandidate,
    incoming: UnifiedPlaceCandidate,
) -> UnifiedPlaceCandidate:
    sources = list(current.sources)
    seen_sources = {(source.type.value, source.url) for source in sources}
    for source in incoming.sources:
        key = (source.type.value, source.url)
        if key not in seen_sources:
            sources.append(source)
            seen_sources.add(key)

    preferred = incoming if incoming.confidence > current.confidence else current
    category = preferred.category
    if category.value == "other":
        category = (
            incoming.category
            if incoming.category.value != "other"
            else current.category
        )
    return UnifiedPlaceCandidate(
        name=preferred.name,
        category=category,
        addressHint=current.address_hint or incoming.address_hint,
        sources=sources,
        confidence=max(current.confidence, incoming.confidence),
        priority=min(current.priority, incoming.priority),
        notes=current.notes or incoming.notes,
    )


def _dedupe_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)
