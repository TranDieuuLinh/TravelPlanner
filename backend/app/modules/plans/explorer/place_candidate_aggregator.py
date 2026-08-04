from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.modules.plans.dto.agent_contracts import PlaceCandidateHint
from app.modules.plans.explorer.schema import (
    PlaceCandidateSource,
    PlaceCandidateSourceType,
    ObservedPlaceAlias,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.place_policy import (
    concise_source_activity,
    is_credible_url_candidate,
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
        # The formatter may return only a subset of a URL itinerary. Always
        # merge deterministic extraction results at candidate level instead of
        # treating one generated URL candidate as proof that the whole source
        # was covered.
        candidates.extend(self._from_url_results(url_results))

        destination_key = _dedupe_key(destination)
        merged: dict[str, UnifiedPlaceCandidate] = {}
        order: list[str] = []
        aliases: dict[str, str] = {}
        for candidate in candidates:
            candidate = _recover_place_name_from_evidence(candidate)
            if not is_credible_url_candidate(candidate):
                continue
            candidate = candidate.model_copy(
                update={
                    "source_activity": concise_source_activity(
                        candidate.source_activity
                    )
                }
            )
            name_key = _dedupe_key(candidate.name)
            identity_key = _place_identity_key(candidate.name, destination)
            # Candidate identity comes only from its normalized place name.
            # sourceOrder is sequencing metadata: independent STT/OCR/caption
            # observations frequently reuse the same order, so using it as an
            # identity key silently merges unrelated venues.
            candidate_aliases = [
                alias
                for alias in (identity_key, name_key)
                if alias
            ]
            key = next(
                (
                    aliases[alias]
                    for alias in candidate_aliases
                    if alias in aliases
                ),
                "",
            )
            if not key:
                key = next(
                    (
                        existing_key
                        for existing_key, existing in merged.items()
                        if _same_place_name(
                            existing.name,
                            candidate.name,
                            destination,
                        )
                    ),
                    identity_key or name_key,
                )
            if not name_key or name_key == destination_key:
                continue
            if key not in merged:
                merged[key] = candidate.model_copy(deep=True)
                order.append(key)
                for alias in candidate_aliases:
                    aliases[alias] = key
                continue
            merged[key] = _merge(
                merged[key],
                candidate,
            )
            for alias in candidate_aliases:
                aliases[alias] = key
        result = [merged[key] for key in order]
        result.sort(
            key=lambda candidate: (
                candidate.source_order is None,
                candidate.source_order or 10_000,
            )
        )
        return result

    def _from_explicit(
        self,
        candidates: list[PlaceCandidateHint],
    ) -> list[UnifiedPlaceCandidate]:
        return [
            UnifiedPlaceCandidate(
                name=candidate.name,
                category=candidate.category,
                addressHint=candidate.address,
                searchRegion=candidate.search_region,
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
                preferenceLevel=candidate.preference_level,
                attributes=candidate.attributes,
                notes=candidate.notes,
                sourceEvidence=candidate.source_evidence,
                sourceOrder=candidate.source_order,
                sourceDay=candidate.source_day,
                sourceTimeHint=candidate.source_time_hint,
                sourceActivity=candidate.source_activity,
                sourceDurationMinutes=candidate.source_duration_minutes,
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
                            alternateNames=detail.aliases,
                            searchNames=detail.aliases,
                            observedAliases=[
                                ObservedPlaceAlias(value=alias, source="stt")
                                for alias in detail.aliases
                                if alias.strip()
                            ],
                            category=detail.category,
                            addressHint=detail.address,
                            searchRegion=detail.search_region,
                            sources=[
                                PlaceCandidateSource(
                                    type=PlaceCandidateSourceType.url,
                                    url=result.url,
                                )
                            ],
                            confidence=(
                                detail.confidence
                                or result.extracted_context.confidence
                            ),
                            preferenceLevel="preferred",
                            attributes=detail.attributes,
                            notes=detail.evidence,
                            sourceEvidence=detail.source_evidence,
                            sourceOrder=detail.source_order,
                            sourceDay=detail.source_day,
                            sourceTimeHint=detail.source_time_hint,
                            sourceActivity=detail.source_activity,
                            sourceDurationMinutes=detail.source_duration_minutes,
                            entityType=detail.entity_type,
                            parentPlace=detail.parent_place,
                            authority=detail.authority,
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


def _recover_place_name_from_evidence(
    candidate: UnifiedPlaceCandidate,
) -> UnifiedPlaceCandidate:
    """Recover a concise place label when extraction appended commentary.

    STT/OCR frequently contains a clean repeated label even when the merged
    ``name`` also contains the following review sentence. Only accept an
    evidenced replacement that is already contained in the original label and
    independently passes the URL-candidate policy.
    """
    if is_credible_url_candidate(candidate):
        return candidate

    original_tokens = _word_tokens(candidate.name)
    for source in ("stt", "ocr", "metadata", "caption"):
        evidence = candidate.source_evidence.get(source)
        if not evidence:
            continue
        recovered = re.sub(
            r"^\s*(?:#?\d{1,2}[.)]|number\s+(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten))\s*",
            "",
            evidence,
            flags=re.IGNORECASE,
        ).strip(" .,;:-")
        recovered_tokens = _word_tokens(recovered)
        if (
            not recovered_tokens
            or not _contains_token_sequence(original_tokens, recovered_tokens)
        ):
            continue
        updated = candidate.model_copy(update={"name": recovered})
        if is_credible_url_candidate(updated):
            return updated
    return candidate


def _merge(
    current: UnifiedPlaceCandidate,
    incoming: UnifiedPlaceCandidate,
    *,
    preserve_current_name: bool = False,
) -> UnifiedPlaceCandidate:
    sources = list(current.sources)
    seen_sources = {(source.type.value, source.url) for source in sources}
    for source in incoming.sources:
        key = (source.type.value, source.url)
        if key not in seen_sources:
            sources.append(source)
            seen_sources.add(key)

    preferred = current if preserve_current_name else max(
        (current, incoming),
        key=_candidate_name_authority,
    )
    search_names = list(
        dict.fromkeys(
            [
                *current.search_names,
                *incoming.search_names,
                *(
                    [incoming.name]
                    if incoming.name != preferred.name
                    else []
                ),
                *(
                    [current.name]
                    if current.name != preferred.name
                    else []
                ),
            ]
        )
    )
    category = preferred.category
    if category.value == "other":
        category = (
            incoming.category
            if incoming.category.value != "other"
            else current.category
        )
    return UnifiedPlaceCandidate(
        name=preferred.name,
        originalName=preferred.original_name,
        englishNames=list(dict.fromkeys([*current.english_names, *incoming.english_names])),
        vietnameseNames=list(dict.fromkeys([*current.vietnamese_names, *incoming.vietnamese_names])),
        alternateNames=list(dict.fromkeys([*current.alternate_names, *incoming.alternate_names])),
        searchNames=search_names,
        observedAliases=_merge_observed_aliases(
            current.observed_aliases,
            incoming.observed_aliases,
        ),
        generatedLookupAliases=[
            *current.generated_lookup_aliases,
            *(
                alias
                for alias in incoming.generated_lookup_aliases
                if alias.value.casefold()
                not in {
                    existing.value.casefold()
                    for existing in current.generated_lookup_aliases
                }
            ),
        ],
        category=category,
        addressHint=current.address_hint or incoming.address_hint,
        searchRegion=incoming.search_region or current.search_region,
        sources=sources,
        sourceEvidence={
            **current.source_evidence,
            **incoming.source_evidence,
        },
        confidence=max(current.confidence, incoming.confidence),
        priority=min(current.priority, incoming.priority),
        preferenceLevel=(
            "must_visit"
            if "must_visit"
            in {
                current.preference_level.value,
                incoming.preference_level.value,
            }
            else "preferred"
            if "preferred"
            in {
                current.preference_level.value,
                incoming.preference_level.value,
            }
            else "mentioned"
        ),
        attributes=list(
            dict.fromkeys([*current.attributes, *incoming.attributes])
        ),
        notes=current.notes or incoming.notes,
        sourceOrder=current.source_order or incoming.source_order,
        sourceDay=current.source_day or incoming.source_day,
        sourceTimeHint=current.source_time_hint or incoming.source_time_hint,
        sourceActivity=concise_source_activity(
            current.source_activity or incoming.source_activity
        ),
        sourceDurationMinutes=(
            current.source_duration_minutes or incoming.source_duration_minutes
        ),
        entityType=preferred.entity_type,
        parentPlace=current.parent_place or incoming.parent_place,
        authority=(
            "high"
            if "high" in {current.authority, incoming.authority}
            else "medium"
            if "medium" in {current.authority, incoming.authority}
            else "low"
        ),
    )


def _merge_observed_aliases(
    *groups: list[ObservedPlaceAlias],
) -> list[ObservedPlaceAlias]:
    aliases: list[ObservedPlaceAlias] = []
    seen: set[tuple[str, str]] = set()
    for alias in (alias for group in groups for alias in group):
        key = (alias.value.casefold(), alias.source)
        if key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases


def _candidate_name_authority(
    candidate: UnifiedPlaceCandidate,
) -> tuple[int, int, float]:
    evidence_rank = next(
        (
            rank
            for source, rank in (
                ("metadata", 4),
                ("caption", 3),
                ("ocr", 2),
                ("stt", 1),
            )
            if candidate.source_evidence.get(source)
        ),
        0,
    )
    authority_rank = {"low": 0, "medium": 1, "high": 2}[candidate.authority]
    return evidence_rank, authority_rank, candidate.confidence


def _dedupe_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def _word_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.findall(r"[a-z0-9]+", without_marks)


def _place_identity_key(name: str, destination: str) -> str:
    name_tokens = _identity_tokens(name, destination)
    return "identity:" + "".join(name_tokens) if name_tokens else ""


def _identity_tokens(name: str, destination: str) -> list[str]:
    name_tokens = _word_tokens(name)
    destination_tokens = _word_tokens(destination)
    if not name_tokens:
        return []
    if destination_tokens:
        destination_width = len(destination_tokens)
        index = 0
        stripped: list[str] = []
        while index < len(name_tokens):
            if name_tokens[index:index + destination_width] == destination_tokens:
                index += destination_width
                continue
            if name_tokens[index] == "".join(destination_tokens):
                index += 1
                continue
            stripped.append(name_tokens[index])
            index += 1
        name_tokens = stripped
    while (
        len(name_tokens) > 2
        and name_tokens[0] in {"a", "an", "the", "very", "famous"}
    ):
        name_tokens = name_tokens[1:]
    return name_tokens


def _same_place_name(left: str, right: str, destination: str) -> bool:
    left_tokens = _identity_tokens(left, destination)
    right_tokens = _identity_tokens(right, destination)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if len(left_tokens) != len(right_tokens):
        return False
    differences = 0
    for left_token, right_token in zip(left_tokens, right_tokens, strict=True):
        if left_token == right_token:
            continue
        if (
            min(len(left_token), len(right_token)) < 3
            or SequenceMatcher(None, left_token, right_token).ratio() < 0.8
        ):
            return False
        differences += 1
    return differences == 1


def _contains_token_sequence(values: list[str], expected: list[str]) -> bool:
    if len(expected) > len(values):
        return False
    return any(
        values[index:index + len(expected)] == expected
        for index in range(len(values) - len(expected) + 1)
    )
