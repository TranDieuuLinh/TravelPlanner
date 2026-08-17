from __future__ import annotations

import hashlib

from app.modules.place_checker.analysis_contract import (
    AnalysisGap,
    CoverageAnalysis,
    GapAnalysis,
)
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    GapStatus,
    GapType,
    IssueSeverity,
    RetrievalSourceKind,
    VerificationStatus,
)
from app.modules.place_checker.errors import (
    CandidateSourceError,
    CandidateSourceTimeout,
)
from app.modules.place_checker.item_contract import ItemResolutionBatch
from app.modules.place_checker.ports import (
    GapCandidateSource,
    PlaceMetadataRepository,
    PromotionOutbox,
)
from app.modules.place_checker.retrieval_enrichment import RetrievalMetadataEnricher
from app.modules.place_checker.retrieval_batch import TargetedRetrievalBatchMixin
from app.modules.place_checker.retrieval_pool_selection import (
    select_adaptive_pool_specs,
)
from app.modules.place_checker.retrieval_contract import (
    GapRetrievalResult,
    PromotionEvent,
    RetrievalAttempt,
    RetrievalBatch,
    RetrievalEvidence,
    RetrievedCandidate,
    TargetedRetrievalQuery,
)
from app.modules.place_checker.pool_policy import (
    activity_pool_target_for_days,
    entertainment_pool_target_for_days,
    per_gap_pool_target,
    pool_query_limit_for_days,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity


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
    "pool:food_alternatives": (GapType.food_coverage, "restaurant", "restaurant"),
    "pool:drink_alternatives": (GapType.food_coverage, "cafe", "cafe"),
    "pool:entertainment_alternatives": (
        GapType.time_of_day,
        "entertainment show games",
        "entertainment",
    ),
    "pool:culture_alternatives": (
        GapType.experience_coverage,
        "culture museum heritage",
        "travel place",
    ),
    "pool:nature_alternatives": (
        GapType.experience_coverage,
        "nature lake garden",
        "travel place",
    ),
    "pool:shopping_alternatives": (
        GapType.experience_coverage,
        "shopping market craft",
        "travel place",
    ),
    "pool:nightlife_alternatives": (
        GapType.time_of_day,
        "nightlife evening entertainment",
        "travel place",
    ),
    "pool:workshop_alternatives": (
        GapType.experience_coverage,
        "workshop class hands-on",
        "travel place",
    ),
    "pool:performance_alternatives": (
        GapType.experience_coverage,
        "performance theater show",
        "travel place",
    ),
    "pool:outdoor_alternatives": (
        GapType.experience_coverage,
        "outdoor walking cycling",
        "travel place",
    ),
    "pool:family_alternatives": (
        GapType.people_accessibility,
        "family children entertainment",
        "travel place",
    ),
    "pool:special_experience_alternatives": (
        GapType.experience_coverage,
        "special experience local culture",
        "travel place",
    ),
    "pool:local_activity_alternatives": (
        GapType.experience_coverage,
        "local activity authentic experience",
        "travel place",
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
    "pool:travel_place_reserve": (
        GapType.experience_coverage,
        "culture museum heritage",
        "travel place",
    ),
}

POOL_RELATION_TERMS = {
    "pool:culture_alternatives": ["văn hóa", "tham quan", "heritage", "museum"],
    "pool:nature_alternatives": [
        "ngoài trời",
        "đi dạo",
        "cắm trại",
        "nature",
        "garden",
        "lake",
    ],
    "pool:shopping_alternatives": [
        "mua sắm",
        "khám phá",
        "hoạt động mua bán địa phương",
        "market",
        "craft",
    ],
    "pool:nightlife_alternatives": [
        "cuộc sống về đêm",
        "nightlife",
        "ăn nhậu",
        "karaoke",
    ],
    "pool:workshop_alternatives": ["làm đồ thủ công", "workshop", "pottery", "class"],
    "pool:performance_alternatives": [
        "văn hóa & giải trí",
        "vui chơi & giải trí",
        "performance",
        "theater",
        "show",
    ],
    "pool:outdoor_alternatives": [
        "ngoài trời",
        "đi dạo",
        "cắm trại",
        "cưỡi ngựa",
        "climbing",
    ],
    "pool:family_alternatives": ["vui chơi & giải trí", "trẻ em", "family", "children"],
    "pool:special_experience_alternatives": [
        "trải nghiệm",
        "văn hóa",
        "làm đồ thủ công",
        "đi dạo",
    ],
    "pool:local_activity_alternatives": [
        "hoạt động mua bán địa phương",
        "làm đồ thủ công",
        "local",
        "craft",
    ],
}


class TargetedRetrievalService(TargetedRetrievalBatchMixin):
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
        retrieval_gaps = list(gaps.gaps)
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
                                gap_id == "pool:food_alternatives"
                                and item.item.item_type == "food"
                            )
                            or (
                                gap_id == "pool:drink_alternatives"
                                and item.item.item_type == "drink"
                            )
                        ]
                        if gap_id
                        in {
                            "pool:food_alternatives",
                            "pool:drink_alternatives",
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

    @classmethod
    def _verify(
        cls,
        evidence: list[RetrievalEvidence],
        query: TargetedRetrievalQuery,
    ) -> list[RetrievedCandidate]:
        groups: list[list[RetrievalEvidence]] = []
        for item in evidence:
            group = next(
                (group for group in groups if cls._same_place(group[0], item)),
                None,
            )
            if group is None:
                groups.append([item])
            else:
                group.append(item)
        candidates = [cls._candidate(group, query) for group in groups]
        conflicting_names = cls._conflicting_names(groups)
        candidates = [
            candidate.model_copy(
                update={
                    "verification_status": VerificationStatus.needs_review,
                    "planner_eligible": False,
                    "conflicts": [*candidate.conflicts, "provider_identity_conflict"],
                }
            )
            if normalize_text(candidate.canonical_name) in conflicting_names
            else candidate
            for candidate in candidates
        ]
        return sorted(
            candidates,
            key=lambda item: (
                not item.planner_eligible,
                -max(source.confidence for source in item.evidence),
                normalize_text(item.canonical_name),
            ),
        )

    @staticmethod
    def _candidate(
        evidence: list[RetrievalEvidence],
        query: TargetedRetrievalQuery,
    ) -> RetrievedCandidate:
        representative = max(evidence, key=lambda item: item.confidence)
        linked_entity = next(
            (item.entity_id for item in evidence if item.entity_id), None
        )
        has_verified_kg_link = any(
            item.entity_id is not None
            and item.source_kind == RetrievalSourceKind.knowledge_graph
            and item.is_verified
            for item in evidence
        )
        external_providers = {
            item.provider
            for item in evidence
            if item.source_kind == RetrievalSourceKind.external
        }
        adm_matches = all(item.adm_id in {None, query.adm_id} for item in evidence)
        if not adm_matches:
            status = VerificationStatus.needs_review
        elif has_verified_kg_link:
            status = VerificationStatus.verified_kg
        elif len(external_providers) >= 2:
            status = VerificationStatus.verified_external
        else:
            status = VerificationStatus.provisional
        metadata = next((item.metadata for item in evidence if item.metadata), None)
        key_source = linked_entity or ":".join(
            [
                normalize_text(representative.name),
                normalize_text(representative.adm_id or query.adm_id),
                normalize_text(representative.category),
            ]
        )
        return RetrievedCandidate(
            candidate_key=key_source[:300],
            gap_id=query.gap_id,
            gap_type=query.gap_type,
            gap_severity=query.severity,
            canonical_name=representative.name,
            place_id=linked_entity,
            adm_id=representative.adm_id or query.adm_id,
            region_key=representative.region_key,
            category=representative.category,
            pool_category=(
                query.gap_id.removeprefix("pool:").removesuffix("_alternatives")
                if query.gap_id.startswith("pool:")
                else None
            ),
            experience_type=representative.experience_type,
            address=representative.address,
            coordinates=representative.coordinates,
            tags=list(dict.fromkeys(tag for item in evidence for tag in item.tags)),
            metadata=metadata,
            relationship_score=max(item.relationship_score for item in evidence),
            relationships=list(
                {
                    (
                        relationship.relationship_type,
                        relationship.from_entity_id,
                        relationship.to_entity_id,
                    ): relationship
                    for item in evidence
                    for relationship in item.relationships
                }.values()
            ),
            verification_status=status,
            planner_eligible=status
            in {
                VerificationStatus.verified_kg,
                VerificationStatus.verified_external,
            },
            evidence=evidence,
            warnings=(
                ["Mới có một nguồn ngoài; chưa được đưa vào Planner."]
                if status == VerificationStatus.provisional
                else []
            ),
        )

    @staticmethod
    def _same_place(left: RetrievalEvidence, right: RetrievalEvidence) -> bool:
        if left.entity_id and left.entity_id == right.entity_id:
            return True
        if (
            left.provider == right.provider
            and left.provider_id
            and (left.provider_id == right.provider_id)
        ):
            return True
        if text_similarity(left.name, right.name) < 0.88:
            return False
        if left.adm_id and right.adm_id and left.adm_id != right.adm_id:
            return False
        if (
            left.category
            and right.category
            and (normalize_text(left.category) != normalize_text(right.category))
        ):
            return False
        if left.coordinates and right.coordinates:
            return distance_km(left.coordinates, right.coordinates) <= 0.5
        return bool(
            left.address
            and right.address
            and text_similarity(left.address, right.address) >= 0.7
        )

    @staticmethod
    def _conflicting_names(
        groups: list[list[RetrievalEvidence]],
    ) -> set[str]:
        conflicts: set[str] = set()
        representatives = [group[0] for group in groups]
        for index, left in enumerate(representatives):
            for right in representatives[index + 1 :]:
                if normalize_text(left.name) != normalize_text(right.name):
                    continue
                same_adm = (
                    not left.adm_id or not right.adm_id or left.adm_id == right.adm_id
                )
                if same_adm:
                    conflicts.add(normalize_text(left.name))
        return conflicts

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
    def _verified_count(candidates: list[RetrievedCandidate]) -> int:
        return sum(candidate.planner_eligible for candidate in candidates)

    @staticmethod
    def _query(
        gap: AnalysisGap,
        context: TripEvaluationContext,
        items: ItemResolutionBatch | None,
        *,
        anchor_place_ids: list[str],
        limit: int | None = None,
    ) -> TargetedRetrievalQuery:
        destination = context.destination
        assert destination.adm_id is not None
        assert destination.canonical_name is not None
        assert destination.country_code is not None
        item_names: list[str] = []
        if items is not None:
            indexes = set(gap.related_item_indexes)
            item_names = [
                item.normalized_requirement
                for item in items.items
                if item.item_index in indexes
            ]
        category = CATEGORY_BY_GAP.get(gap.gap_type)
        intent = (
            ", ".join(item_names)
            or INTENT_BY_GAP.get(gap.gap_type)
            or category
            or gap.gap_type.value
        )
        people_tags = []
        if context.people.children:
            people_tags.append("children_suitable")
        if context.people.infants:
            people_tags.append("infants_suitable")
        pool_spec = {
            **CORE_POOL_QUERY_SPECS,
            **POOL_QUERY_SPECS,
        }.get(gap.gap_id)
        query_text = pool_spec[1] if pool_spec else intent
        if gap.gap_id == "pool:food_alternatives" and item_names:
            query_text = f"{', '.join(item_names)} restaurant"
        elif gap.gap_id == "pool:drink_alternatives" and item_names:
            query_text = f"{', '.join(item_names)} cafe"
        query_limit = limit or per_gap_pool_target(context.days, 1)
        if gap.gap_id in CORE_POOL_QUERY_SPECS:
            query_limit = pool_query_limit_for_days(context.days)
        elif gap.gap_type == GapType.food_coverage:
            query_limit = max(query_limit, min(60, context.days * 3))
        elif gap.gap_id == "pool:entertainment_alternatives":
            query_limit = max(
                query_limit,
                min(60, entertainment_pool_target_for_days(context.days)),
            )
        elif category == "travel_place" and query_text == "travel place":
            query_limit = max(
                query_limit,
                min(60, activity_pool_target_for_days(context.days)),
            )
        return TargetedRetrievalQuery(
            gap_id=gap.gap_id,
            gap_type=gap.gap_type,
            severity=gap.severity,
            # ADM is a structured filter. Repeating its display name in the
            # text query would favor venues merely containing that city name.
            query_text=query_text,
            adm_id=destination.adm_id,
            adm_name=destination.canonical_name,
            country_code=destination.country_code,
            category_hint={**CORE_POOL_QUERY_SPECS, **POOL_QUERY_SPECS}.get(
                gap.gap_id,
                (None, None, category),
            )[2]
            if gap.gap_id in {*CORE_POOL_QUERY_SPECS, *POOL_QUERY_SPECS}
            else category,
            budget_level=context.budget.level,
            people_tags=people_tags,
            time_hints=[],
            anchor_place_ids=list(dict.fromkeys(anchor_place_ids))[:10],
            relation_terms=POOL_RELATION_TERMS.get(gap.gap_id, []),
            # Longer trips need a wider reserve, while PlaceChecker still
            # leaves day assignment and route ordering to the final planner.
            limit=query_limit,
        )
