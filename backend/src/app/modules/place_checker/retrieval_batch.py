"""Batch orchestration for targeted PlaceChecker retrieval."""

from __future__ import annotations

from app.modules.place_checker.retrieval_contract import (
    GapRetrievalResult,
    RetrievalAttempt,
)


class TargetedRetrievalBatchMixin:
    async def _retrieve_queries(self, queries):
        batch_search = getattr(self.knowledge_graph, "search_many", None)
        if batch_search is None:
            results = []
            event_ids = []
            warnings = []
            external_calls_remaining = self.external_call_budget
            for query in queries:
                result = await self._retrieve_gap(
                    query,
                    allow_external=external_calls_remaining > 0,
                )
                if any(
                    attempt.source_kind.value == "external"
                    for attempt in result.attempts
                ):
                    external_calls_remaining -= 1
                queued, queue_warnings = await self._queue_promotions(
                    result.candidates
                )
                results.append(result)
                event_ids.extend(queued)
                warnings.extend(queue_warnings)
            return results, event_ids, warnings

        source_items = await batch_search(queries, max_concurrency=4)
        results = []
        external_calls_remaining = self.external_call_budget
        for query, source_item in zip(queries, source_items):
            evidence = list(source_item.evidence)
            attempts = [
                RetrievalAttempt(
                    provider=self.knowledge_graph.provider_name,
                    source_kind=self.knowledge_graph.source_kind,
                    outcome=source_item.outcome,
                    candidate_count=len(evidence),
                    error_code=source_item.error_code,
                )
            ]
            warnings = self._source_warnings(
                self.knowledge_graph.provider_name,
                source_item.outcome,
            )
            for source in self.internal_sources:
                evidence.extend(
                    await self._call_source(source, query, attempts, warnings)
                )
            if not evidence and external_calls_remaining > 0:
                external_calls_remaining -= 1
                verified_target = min(
                    query.limit,
                    max(1, self.verified_target_per_gap),
                )
                for source in self.external_sources:
                    evidence.extend(
                        await self._call_source(source, query, attempts, warnings)
                    )
                    if self._verified_count(self._verify(evidence, query)) >= verified_target:
                        break
            results.append(
                GapRetrievalResult(
                    gap_id=query.gap_id,
                    query=query,
                    candidates=self._verify(evidence, query)[: query.limit],
                    attempts=attempts,
                    warnings=warnings,
                )
            )

        await self._enrich_results_once(results)
        event_ids = []
        warnings = []
        for result in results:
            queued, queue_warnings = await self._queue_promotions(result.candidates)
            event_ids.extend(queued)
            warnings.extend(queue_warnings)
        return results, event_ids, warnings

    async def _enrich_results_once(self, results) -> None:
        candidates = [candidate for result in results for candidate in result.candidates]
        enriched, metadata_warnings = await self.metadata_enricher.enrich(candidates)
        offset = 0
        for result in results:
            size = len(result.candidates)
            result.candidates = enriched[offset : offset + size]
            if metadata_warnings:
                result.warnings = list(
                    dict.fromkeys([*result.warnings, *metadata_warnings])
                )
            offset += size

    @staticmethod
    def _source_warnings(provider: str, outcome: str) -> list[str]:
        if outcome == "timeout":
            return [f"Nguồn {provider} hết thời gian chờ."]
        if outcome == "error":
            return [f"Nguồn {provider} tạm thời lỗi."]
        return []
