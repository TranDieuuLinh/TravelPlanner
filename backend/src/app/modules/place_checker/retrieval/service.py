from __future__ import annotations

import hashlib

from app.modules.place_checker.analysis.contract import (
    AnalysisGap,
    CoverageAnalysis,
    GapAnalysis,
)
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    GapStatus,
    GapType,
    IssueSeverity,
    VerificationStatus,
)
from app.modules.place_checker.errors import (
    CandidateSourceError,
    CandidateSourceTimeout,
)
from app.modules.place_checker.resolution.item_contract import ItemResolutionBatch
from app.modules.place_checker.ports import (
    GapCandidateSource,
    PlaceMetadataRepository,
    PromotionOutbox,
)
from app.modules.place_checker.retrieval.enrichment import RetrievalMetadataEnricher
from app.modules.place_checker.retrieval.batch import TargetedRetrievalBatchMixin
from app.modules.place_checker.retrieval.pool_selection import (
    select_adaptive_pool_specs,
)
from app.modules.place_checker.retrieval.contract import (
    GapRetrievalResult,
    PromotionEvent,
    RetrievalAttempt,
    RetrievalBatch,
    RetrievalEvidence,
    RetrievedCandidate,
    TargetedRetrievalQuery,
)
from app.modules.place_checker.selection.pool_policy import per_gap_pool_target
from app.modules.place_checker.retrieval.query import build_targeted_query
from app.modules.place_checker.retrieval.verification import RetrievalVerificationMixin


DISCOVERY_GAPS = {
    GapType.trip_capacity,
    GapType.experience_coverage,
    GapType.food_coverage,
    GapType.time_of_day,
    GapType.budget,
    GapType.diversity,
    GapType.geographic_balance,
    GapType.people_accessibility,
}

CATEGORY_BY_GAP = {
    GapType.trip_capacity: "travel_place",
    GapType.food_coverage: "restaurant",
    GapType.experience_coverage: "travel_place",
    GapType.time_of_day: "travel_place",
    GapType.budget: "travel_place",
    GapType.diversity: "travel_place",
    GapType.geographic_balance: "travel_place",
    GapType.people_accessibility: "travel_place",
}

INTENT_BY_GAP = {
    GapType.trip_capacity: "travel place",
    GapType.experience_coverage: "travel place",
    GapType.food_coverage: "restaurant",
    GapType.time_of_day: "travel place",
    GapType.budget: "travel place",
    GapType.diversity: "travel place",
    GapType.geographic_balance: "travel place",
    GapType.people_accessibility: "travel place",
}

POOL_QUERY_SPECS = {
    "pool:restaurant_candidates": (
        GapType.food_coverage,
        "restaurant",
        "restaurant",
    ),
    "pool:drink_dessert_candidates": (
        GapType.time_of_day,
        "cafe",
        "cafe",
    ),
    "pool:entertainment_candidates": (
        GapType.time_of_day,
        "entertainment",
        "entertainment",
    ),
}

CORE_POOL_QUERY_SPECS = {
    "pool:travel_place_candidates": (
        GapType.experience_coverage,
        "travel place",
        "travel place",
    ),
    "pool:accommodation_candidates": (
        GapType.budget,
        "hotel",
        "accommodation",
    ),
}

POOL_RELATION_TERMS: dict[str, list[str]] = {}


class TargetedRetrievalService(
    TargetedRetrievalBatchMixin,
    RetrievalVerificationMixin,
):
    def __init__(
        self,
        knowledge_graph: GapCandidateSource,
        *,
        internal_sources: list[GapCandidateSource] | None = None,
        external_sources: list[GapCandidateSource] | None = None,
        metadata_repository: PlaceMetadataRepository | None = None,
        promotion_outbox: PromotionOutbox | None = None,
        verified_target_per_gap: int = 5,
        external_call_budget: int = 5,
        expand_pool: bool = False,
        ensure_core_pools: bool = False,
    ) -> None:
        self.knowledge_graph = knowledge_graph
        self.internal_sources = internal_sources or []
        self.external_sources = (external_sources or [])[:2]
        self.metadata_enricher = RetrievalMetadataEnricher(metadata_repository)
        self.promotion_outbox = promotion_outbox
        self.verified_target_per_gap = verified_target_per_gap
        self.external_call_budget = max(0, external_call_budget)
        self.expand_pool = expand_pool
        self.ensure_core_pools = ensure_core_pools

    async def retrieve(
        self,
        gaps: GapAnalysis,
        context: TripEvaluationContext,
        items: ItemResolutionBatch | None = None,
        anchor_place_ids: list[str] | None = None,
        excluded_gap_types: set[GapType] | None = None,
        coverage: CoverageAnalysis | None = None,
    ) -> RetrievalBatch:
        results: list[GapRetrievalResult] = []
        event_ids: list[str] = []
        warnings: list[str] = []
        retrieval_gaps = (
            [gap for gap in gaps.gaps if gap.gap_type not in DISCOVERY_GAPS]
            if self.expand_pool or self.ensure_core_pools
            else list(gaps.gaps)
        )
        existing_gap_ids = {gap.gap_id for gap in retrieval_gaps}
        # A resolved input item is not a reason to stop collecting alternatives.
        # The final planner still needs enough restaurants, drinks and activities
        # to choose from day by day. Different intents prevent one broad query
        # from returning the same small group of places repeatedly.
        excluded_gap_types = excluded_gap_types or set()
        pool_specs = select_adaptive_pool_specs(
            {
                **(CORE_POOL_QUERY_SPECS if self.ensure_core_pools else {}),
                **(POOL_QUERY_SPECS if self.expand_pool else {}),
            },
            gaps.gaps,
            coverage,
            days=context.days,
            excluded_gap_types=excluded_gap_types,
        )
        for gap_id, (gap_type, intent, category) in pool_specs.items():
            if gap_id in existing_gap_ids:
                continue
            retrieval_gaps.append(
                AnalysisGap(
                    gap_id=gap_id,
                    gap_type=gap_type,
                    severity=IssueSeverity.low,
                    trigger=f"Cần pool bổ sung theo nhóm {intent}.",
                    suggested_action=f"Tìm thêm địa điểm thuộc nhóm {category}.",
                    related_item_indexes=(
                        [
                            item.item_index
                            for item in (items.items if items else [])
                            if (
                                gap_id == "pool:restaurant_candidates"
                                and item.item.item_type == "food"
                            )
                            or (
                                gap_id == "pool:drink_dessert_candidates"
                                and item.item.item_type == "drink"
                            )
                        ]
                        if gap_id
                        in {
                            "pool:restaurant_candidates",
                            "pool:drink_dessert_candidates",
                        }
                        else []
                    ),
                )
            )
        discovery_gap_count = sum(
            gap.gap_type in DISCOVERY_GAPS
            for gap in retrieval_gaps
            if gap.status == GapStatus.open
        )
        per_gap_limit = per_gap_pool_target(context.days, discovery_gap_count)
        pending_queries: list[TargetedRetrievalQuery] = []
        static_results: list[GapRetrievalResult] = []
        for gap in retrieval_gaps:
            if gap.status != GapStatus.open:
                continue
            if gap.gap_type in excluded_gap_types:
                continue
            query = self._query(
                gap,
                context,
                items,
                anchor_place_ids=anchor_place_ids or [],
                limit=per_gap_limit,
            )
            if gap.gap_type not in DISCOVERY_GAPS:
                static_results.append(
                    GapRetrievalResult(
                        gap_id=gap.gap_id,
                        query=query,
                        warnings=[
                            "Gap này cần xác minh/làm giàu, không thêm place mới."
                        ],
                    )
                )
                continue
            pending_queries.append(query)
        retrieved, queued, queue_warnings = await self._retrieve_queries(
            pending_queries
        )
        results.extend([*static_results, *retrieved])
        event_ids.extend(queued)
        warnings.extend(queue_warnings)
        return RetrievalBatch(
            gaps=results,
            promotion_event_ids=list(dict.fromkeys(event_ids)),
            warnings=list(dict.fromkeys(warnings)),
        )

    async def _retrieve_gap(
        self,
        query: TargetedRetrievalQuery,
        *,
        allow_external: bool = True,
    ) -> GapRetrievalResult:
        evidence: list[RetrievalEvidence] = []
        attempts: list[RetrievalAttempt] = []
        warnings: list[str] = []
        verified_target = min(query.limit, max(1, self.verified_target_per_gap))
        for source in [self.knowledge_graph, *self.internal_sources]:
            evidence.extend(await self._call_source(source, query, attempts, warnings))
            candidates = self._verify(evidence, query)
            if self._verified_count(candidates) >= verified_target:
                break
        # Keep the ranked top-K returned by the catalog even when it does not
        # fill the preferred target. Browser search is a last resort only when
        # the database has no usable evidence for this gap.
        if allow_external and not evidence:
            for source in self.external_sources:
                evidence.extend(
                    await self._call_source(source, query, attempts, warnings)
                )
                candidates = self._verify(evidence, query)
                if self._verified_count(candidates) >= verified_target:
                    break
        candidates, metadata_warnings = await self.metadata_enricher.enrich(
            self._verify(evidence, query)[: query.limit]
        )
        warnings.extend(metadata_warnings)
        return GapRetrievalResult(
            gap_id=query.gap_id,
            query=query,
            candidates=candidates,
            attempts=attempts,
            warnings=warnings,
        )

    @staticmethod
    async def _call_source(
        source: GapCandidateSource,
        query: TargetedRetrievalQuery,
        attempts: list[RetrievalAttempt],
        warnings: list[str],
    ) -> list[RetrievalEvidence]:
        try:
            found = await source.search(query)
        except CandidateSourceTimeout as exc:
            attempts.append(
                RetrievalAttempt(
                    provider=source.provider_name,
                    source_kind=source.source_kind,
                    outcome="timeout",
                    error_code=exc.code,
                )
            )
            warnings.append(f"Nguồn {source.provider_name} hết thời gian chờ.")
            return []
        except CandidateSourceError as exc:
            attempts.append(
                RetrievalAttempt(
                    provider=source.provider_name,
                    source_kind=source.source_kind,
                    outcome="error",
                    error_code=exc.code,
                )
            )
            warnings.append(f"Nguồn {source.provider_name} tạm thời lỗi.")
            return []
        except Exception:
            attempts.append(
                RetrievalAttempt(
                    provider=source.provider_name,
                    source_kind=source.source_kind,
                    outcome="error",
                    error_code="unexpected_candidate_source_error",
                )
            )
            warnings.append(f"Nguồn {source.provider_name} gặp lỗi không xác định.")
            return []
        normalized = [
            item.model_copy(
                update={
                    "provider": source.provider_name,
                    "source_kind": source.source_kind,
                }
            )
            for item in found[: query.limit]
        ]
        attempts.append(
            RetrievalAttempt(
                provider=source.provider_name,
                source_kind=source.source_kind,
                outcome="candidates" if normalized else "empty",
                candidate_count=len(normalized),
            )
        )
        return normalized

    async def _queue_promotions(
        self,
        candidates: list[RetrievedCandidate],
    ) -> tuple[list[str], list[str]]:
        if self.promotion_outbox is None:
            return [], []
        event_ids: list[str] = []
        warnings: list[str] = []
        for candidate in candidates:
            if candidate.verification_status != VerificationStatus.verified_external:
                continue
            event_id = (
                "place-promotion:"
                + hashlib.sha256(candidate.candidate_key.encode("utf-8")).hexdigest()[
                    :24
                ]
            )
            try:
                await self.promotion_outbox.enqueue(
                    PromotionEvent(event_id=event_id, candidate=candidate)
                )
                event_ids.append(event_id)
            except Exception:
                warnings.append(
                    f"Không thể queue promotion cho {candidate.canonical_name}."
                )
        return event_ids, warnings

    @staticmethod
    def _query(
        gap: AnalysisGap,
        context: TripEvaluationContext,
        items: ItemResolutionBatch | None,
        *,
        anchor_place_ids: list[str],
        limit: int | None = None,
    ) -> TargetedRetrievalQuery:
        return build_targeted_query(
            gap,
            context,
            items,
            anchor_place_ids=anchor_place_ids,
            limit=limit,
            core_specs=CORE_POOL_QUERY_SPECS,
            pool_specs=POOL_QUERY_SPECS,
            category_by_gap=CATEGORY_BY_GAP,
            intent_by_gap=INTENT_BY_GAP,
            relation_terms=POOL_RELATION_TERMS,
        )
