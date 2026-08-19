"""Batch candidate generation for compatible knowledge-graph searches."""

from __future__ import annotations

import asyncio
import time

from app.shared.tools.search_places.contract import PlaceSearchRequest, PlaceSearchResult
from app.shared.tools.search_places.normalization import lookup_names
from app.shared.tools.search_places.ports import (
    PlaceSearchProviderError,
    PlaceSearchProviderTimeout,
)
from app.shared.tools.search_places.scoring import rank_candidates


class SearchPlacesBatchMixin:
    async def search_many(
        self,
        requests: list[PlaceSearchRequest],
    ) -> list[PlaceSearchResult]:
        provider_search = getattr(self.knowledge_graph, "search_many", None)
        if not requests or provider_search is None or not self._batch_compatible(requests):
            return list(await asyncio.gather(*(self.search(item) for item in requests)))

        started_at = time.perf_counter()
        name_batches = [
            lookup_names(request.query, request.alternate_names)
            for request in requests
        ]
        first = requests[0]
        try:
            candidate_batches = await provider_search(
                name_batches,
                input_adm=first.input_adm,
                place_type_hint=first.place_type_hint,
                limit=first.top_k,
                anchor_place_ids=[request.anchor_place_id for request in requests],
            )
        except (PlaceSearchProviderTimeout, PlaceSearchProviderError) as exc:
            return [self._provider_failure(request, names, started_at, exc) for request, names in zip(requests, name_batches)]

        results = []
        for request, names, candidates in zip(requests, name_batches, candidate_batches):
            matches = rank_candidates(request, self._deduplicate(candidates))
            attempt = self._attempt(
                self.knowledge_graph.provider_name,
                "candidates" if candidates else "empty",
                names,
                started_at,
                candidate_count=len(candidates),
            )
            decision = self._decide(request, matches)
            if decision is not None:
                status, selected, reason = decision
                results.append(self._result(
                    request,
                    status=status,
                    selected=selected,
                    matches=matches,
                    attempts=[attempt],
                    reason=reason,
                ))
            else:
                results.append(self._result(
                    request,
                    status="unresolved",
                    matches=matches,
                    attempts=[attempt],
                    reason="external_fallback_disabled",
                ))
        return results

    def _provider_failure(self, request, names, started_at, exc):
        outcome = "timeout" if isinstance(exc, PlaceSearchProviderTimeout) else "error"
        attempt = self._attempt(
            self.knowledge_graph.provider_name,
            outcome,
            names,
            started_at,
            error_code=exc.code,
        )
        return self._result(
            request,
            status="provider_error",
            matches=[],
            attempts=[attempt],
            reason="knowledge_graph_provider_error",
            retryable=True,
        )

    def _batch_compatible(self, requests: list[PlaceSearchRequest]) -> bool:
        first = requests[0]
        return all(
            request.input_adm == first.input_adm
            and request.place_type_hint == first.place_type_hint
            and request.top_k == first.top_k
            and request.provider_scope != "external"
            and (not request.allow_external_fallback or self.external is None)
            for request in requests
        )
