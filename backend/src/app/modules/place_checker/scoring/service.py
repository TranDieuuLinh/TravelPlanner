from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from app.modules.explorer.public import YamlTagCatalog
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import CostTier, VerificationStatus
from app.modules.place_checker.evaluation.avoidance import has_avoid_conflict
from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.evaluation.price_policy import planner_cost
from app.modules.place_checker.retrieval.contract import (
    RetrievalBatch,
    RetrievedCandidate,
)
from app.modules.place_checker.scoring.contract import (
    CandidateRankingBatch,
    CandidateScoreComponents,
    ScoredCandidate,
)
from app.modules.place_checker.scoring.existing import existing_pool_signals
from app.modules.place_checker.scoring.policy import SEVERITY_VALUE, hard_violations
from app.modules.place_checker.scoring.reputation import (
    CategoryReputationProfile,
    build_reputation_profiles,
    reputation_components,
)
from app.modules.place_checker.scoring.reranking import CandidateDiversityReranker
from app.modules.place_checker.scoring.tag_policy import CandidateTagPolicy
from app.modules.place_checker.selection.pool_balancing import CandidatePoolBalancer
from app.modules.place_checker.selection.pool_policy import (
    activity_pool_target_for_days,
    combined_pool_target_for_days,
    drink_dessert_pool_target_for_days,
    entertainment_pool_target_for_days,
    food_pool_target_for_days,
    pool_query_limit_for_days,
)
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity

WEIGHTS = {
    "intent_match": 0.15,
    "preference_match": 0.10,
    "gap_value": 0.13,
    "budget_fit": 0.10,
    "geo_fit": 0.08,
    "people_fit": 0.06,
    "time_fit": 0.07,
    "quality": 0.05,
    "uniqueness": 0.05,
    "data_confidence": 0.05,
    "rating_quality": 0.10,
    "review_quality": 0.06,
}


class CandidateScoringService:
    def __init__(
        self,
        *,
        now: datetime | None = None,
        allowed_tags_provider: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.now = now or datetime.now(UTC)
        catalog = YamlTagCatalog()
        self.allowed_tags_provider = (
            allowed_tags_provider
            or (lambda: catalog.definitions().keys())
        )

    def rank(
        self,
        retrieval: RetrievalBatch,
        context: TripEvaluationContext,
        existing_places: PlaceEvaluationBatch,
        *,
        reserve_limit_per_gap: int | None = None,
        max_total_candidates: int | None = None,
    ) -> CandidateRankingBatch:
        pool_target = max_total_candidates or combined_pool_target_for_days(
            context.days
        )
        if reserve_limit_per_gap is None:
            reserve_limit_per_gap = pool_query_limit_for_days(context.days)
        allowed_tags = frozenset(self.allowed_tags_provider())
        normalized_context = context.model_copy(
            update={
                "preferences": CandidateTagPolicy.filter_intent_tags(
                    context.preferences, allowed_tags
                ),
                "avoids": CandidateTagPolicy.filter_intent_tags(
                    context.avoids, allowed_tags
                ),
            }
        )
        candidates = [
            candidate for gap in retrieval.gaps for candidate in gap.candidates
        ]
        reputation_profiles = build_reputation_profiles(candidates)
        existing_tag_counts, anchors = existing_pool_signals(
            existing_places,
            allowed_tags,
        )
        scored = [
            self._score(
                candidate,
                normalized_context,
                allowed_tags,
                anchors,
                reputation_profiles,
            )
            for candidate in candidates
        ]
        ranked = CandidateDiversityReranker().rerank(
            [item for item in scored if item.eligible],
            reserve_limit_per_gap=reserve_limit_per_gap,
            initial_tag_counts=existing_tag_counts,
        )
        if max_total_candidates is not None:
            existing_count = sum(
                1
                for item in existing_places.places
                if item.place.place_id and item.planner_eligible
            )
            ranked = CandidatePoolBalancer.take_ranked(
                ranked,
                max(0, pool_target - existing_count),
            )
        else:
            ranked = CandidatePoolBalancer.select_entity_type_quotas(
                ranked,
                existing_places,
                activity_target=activity_pool_target_for_days(context.days),
                food_target=food_pool_target_for_days(context.days),
                entertainment_target=entertainment_pool_target_for_days(context.days),
                drink_dessert_target=drink_dessert_pool_target_for_days(context.days),
            )
        excluded = sorted(
            (item for item in scored if not item.eligible),
            key=lambda item: (-item.final_score, item.candidate.candidate_key),
        )
        return CandidateRankingBatch(
            ranked=ranked,
            excluded=excluded,
            reserve_limit_per_gap=reserve_limit_per_gap,
            pool_target=pool_target,
        )

    def _score(
        self,
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
        allowed_tags: frozenset[str],
        anchors: list[Coordinates],
        reputation_profiles: dict[str, CategoryReputationProfile],
    ) -> ScoredCandidate:
        labels = self._labels(candidate)
        selection_tags = CandidateTagPolicy.candidate_tags(candidate, allowed_tags)
        distance = self._nearest_distance(candidate.coordinates, anchors)
        rating_quality, review_quality = reputation_components(
            candidate,
            reputation_profiles,
        )
        components = CandidateScoreComponents(
            intent_match=self._intent_match(candidate, labels),
            preference_match=CandidateTagPolicy.preference_ratio(
                context.preferences,
                selection_tags,
            ),
            gap_value=SEVERITY_VALUE[candidate.gap_severity],
            budget_fit=self._budget_fit(candidate, context),
            geo_fit=self._geo_fit(distance),
            people_fit=self._people_fit(candidate, context),
            time_fit=self._time_fit(candidate, context),
            quality=self._quality(candidate),
            # Dynamic tag diversity is applied by the greedy reranker. Keeping
            # this at zero prevents category/experience diversity from being
            # counted in parallel with the tags-auto policy.
            uniqueness=0.0,
            data_confidence=max(item.confidence for item in candidate.evidence),
            rating_quality=rating_quality,
            review_quality=review_quality,
        )
        component_values = components.model_dump()
        base = sum(WEIGHTS[name] * value for name, value in component_values.items())
        penalties = self._penalties(
            candidate,
            context,
            selection_tags,
            distance,
        )
        penalty_total = min(0.65, sum(penalties.values()))
        exclusion_reasons = hard_violations(candidate, context, set(selection_tags))
        final_score = max(0.0, min(1.0, base - penalty_total))
        return ScoredCandidate(
            candidate=candidate,
            selection_tags=list(selection_tags),
            components=components,
            base_score=round(base, 6),
            penalties=penalties,
            penalty_total=round(penalty_total, 6),
            final_score=round(final_score, 6),
            rerank_score=round(final_score, 6),
            distance_from_anchor_km=distance,
            eligible=not exclusion_reasons,
            exclusion_reasons=exclusion_reasons,
        )

    def _penalties(
        self,
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
        selection_tags: tuple[str, ...],
        distance: float | None,
    ) -> dict[str, float]:
        penalties: dict[str, float] = {}
        if has_avoid_conflict(context.avoids, selection_tags):
            penalties["avoid_conflict"] = 0.25
        tier = candidate.metadata.cost_tier if candidate.metadata else CostTier.unknown
        if context.budget.level == "low" and tier in {CostTier.high, CostTier.premium}:
            penalties["high_cost_mismatch"] = 0.15
        if distance is not None and distance > 15:
            penalties["geographic_outlier"] = 0.25
        elif distance is not None and distance > 8:
            penalties["geographic_outlier"] = 0.10
        if candidate.verification_status not in {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        }:
            penalties["low_verification"] = 0.20
        if any(relationship.is_pending for relationship in candidate.relationships):
            penalties["pending_relationship_evidence"] = 0.04
        fetched_at = candidate.metadata.fetched_at if candidate.metadata else None
        if fetched_at is not None and fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        if fetched_at is not None and fetched_at < self.now - timedelta(days=90):
            penalties["stale_data"] = 0.08
        return penalties

    @classmethod
    def _intent_match(
        cls,
        candidate: RetrievedCandidate,
        labels: set[str],
    ) -> float:
        expected = normalize_text(candidate.gap_type.value.replace("_coverage", ""))
        if any(expected in label or label in expected for label in labels if label):
            return 1.0
        return max(
            (text_similarity(expected, label) for label in labels),
            default=0.5,
        )

    @staticmethod
    def _budget_fit(
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
    ) -> float:
        metadata = candidate.metadata
        tier = metadata.cost_tier if metadata else CostTier.unknown
        if (
            metadata
            and planner_cost(
                category=candidate.category,
                minimum=metadata.minimum_cost,
                typical=metadata.typical_cost,
                maximum=metadata.maximum_cost,
                tier=tier,
            )
            == 0
        ):
            return 1.0
        values = {
            CostTier.free: 1.0,
            CostTier.low: 0.95,
            CostTier.medium: 0.7,
            CostTier.high: 0.35,
            CostTier.premium: 0.1,
            CostTier.unknown: 0.45,
        }
        score = values[tier]
        if context.budget.level == "high":
            return max(score, 0.75)
        if context.budget.level == "medium" and tier == CostTier.medium:
            return 1.0
        return score

    @staticmethod
    def _people_fit(
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
    ) -> float:
        metadata = candidate.metadata
        if metadata is None:
            return 0.5
        checks: list[bool | None] = []
        if context.people.children:
            checks.append(metadata.children_suitable)
        if context.people.infants:
            checks.append(metadata.infants_suitable)
        if not checks:
            return 1.0
        if False in checks:
            return 0.0
        return 1.0 if all(value is True for value in checks) else 0.5

    @staticmethod
    def _time_fit(
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
    ) -> float:
        duration = (
            candidate.metadata.typical_duration_minutes if candidate.metadata else None
        )
        if duration is None:
            return 0.5
        if duration <= context.capacity.typical_minutes:
            return 1.0
        if duration <= context.capacity.maximum_minutes:
            return 0.6
        return 0.0

    @staticmethod
    def _quality(candidate: RetrievedCandidate) -> float:
        metadata = candidate.metadata
        if metadata is None:
            return 0.2
        fields = [
            metadata.coordinates,
            metadata.category,
            metadata.typical_duration_minutes,
            metadata.cost_tier != CostTier.unknown,
            metadata.opening_hours,
            metadata.fetched_at,
        ]
        return sum(value is not None and value is not False for value in fields) / len(
            fields
        )

    @staticmethod
    def _geo_fit(distance: float | None) -> float:
        if distance is None:
            return 0.5
        if distance <= 2:
            return 1.0
        if distance <= 8:
            return 0.75
        if distance <= 20:
            return 0.4
        return 0.1

    @staticmethod
    def _nearest_distance(
        coordinates: Coordinates | None,
        anchors: list[Coordinates],
    ) -> float | None:
        if coordinates is None or not anchors:
            return None
        return min(distance_km(coordinates, anchor) for anchor in anchors)

    @staticmethod
    def _labels(candidate: RetrievedCandidate) -> set[str]:
        return {
            normalize_text(value)
            for value in [
                candidate.canonical_name,
                candidate.category or "",
                candidate.experience_type or "",
                candidate.pool_category or "",
                *candidate.tags,
                *(candidate.metadata.tags if candidate.metadata else []),
            ]
            if value
        }
