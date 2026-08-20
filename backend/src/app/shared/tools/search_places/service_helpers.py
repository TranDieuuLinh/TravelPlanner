"""Pure result, deduplication and disambiguation helpers for search_places."""

import time

from app.shared.tools.search_places.contract import (
    PlaceProviderCandidate,
    PlaceSearchMatch,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderAttempt,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity


class SearchPlacesHelpersMixin:
    @classmethod
    def _deduplicate(cls, candidates):
        selected: list[PlaceProviderCandidate] = []
        for candidate in candidates:
            duplicate_index = next(
                (
                    index
                    for index, existing in enumerate(selected)
                    if cls._same_physical_place(existing, candidate)
                ),
                None,
            )
            if duplicate_index is None:
                selected.append(candidate)
            elif candidate.data_confidence > selected[duplicate_index].data_confidence:
                selected[duplicate_index] = candidate
        return selected

    @staticmethod
    def _same_physical_place(left, right) -> bool:
        if left.stable_id and left.stable_id == right.stable_id:
            return True
        if normalize_text(left.name) != normalize_text(right.name):
            return False
        if normalize_text(left.canonical_type) != normalize_text(right.canonical_type):
            return False
        if (
            left.address
            and right.address
            and text_similarity(left.address, right.address) < 0.5
        ):
            return False
        if left.coordinates is None or right.coordinates is None:
            return False
        return distance_km(left.coordinates, right.coordinates) <= 0.2

    @staticmethod
    def _distinctive_name_disambiguates(top, second) -> bool:
        top_name = top.score_components.get("nameSimilarity", 0)
        second_name = second.score_components.get("nameSimilarity", 0)
        return top_name >= 0.94 and top_name - second_name >= 0.07

    @staticmethod
    def _address_hint_disambiguates(request, top, second) -> bool:
        if not request.address_hint:
            return False
        top_address = top.score_components.get("addressCompatibility", 0)
        second_address = second.score_components.get("addressCompatibility", 0)
        return top_address >= 0.70 and top_address - second_address >= 0.15

    @staticmethod
    def _route_context_disambiguates(top, second) -> bool:
        top_distance = top.score_components.get("anchorDistanceKm")
        second_distance = second.score_components.get("anchorDistanceKm")
        if top_distance is None or second_distance is None:
            return False
        return (
            top_distance <= 15
            and second_distance - top_distance >= 0.75
            and second_distance > 0
            and top_distance <= second_distance * 0.70
        )

    @staticmethod
    def _merge_matches(first, second, limit):
        matches: dict[str, PlaceSearchMatch] = {}
        for match in [*first, *second]:
            identity = match.place_id or (
                f"{match.provider}:{normalize_text(match.name)}:"
                f"{normalize_text(match.address)}"
            )
            current = matches.get(identity)
            if current is None or match.score > current.score:
                matches[identity] = match
        return sorted(
            matches.values(),
            key=lambda match: (bool(match.rejection_reasons), -match.score),
        )[:limit]

    @staticmethod
    def _attempt(
        provider,
        outcome,
        queries,
        started_at,
        *,
        candidate_count=0,
        error_code=None,
    ) -> ProviderAttempt:
        return ProviderAttempt(
            provider=provider,
            outcome=outcome,
            queries=queries,
            candidateCount=candidate_count,
            durationMs=max(0, round((time.perf_counter() - started_at) * 1000)),
            errorCode=error_code,
        )

    @staticmethod
    def _result(
        request: PlaceSearchRequest,
        *,
        status,
        matches,
        attempts,
        reason,
        selected=None,
        retryable=False,
    ) -> PlaceSearchResult:
        return PlaceSearchResult(
            status=status,
            query=request.query,
            normalizedQuery=normalize_text(request.query),
            searchMode=request.search_mode,
            selected=selected,
            topMatches=matches,
            providerAttempts=attempts,
            resolutionReason=reason,
            retryable=retryable,
        )
