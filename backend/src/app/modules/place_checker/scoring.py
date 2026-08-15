from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    CostTier,
    VerificationStatus,
)
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.pool_policy import (
    activity_pool_target_for_days,
    combined_pool_target_for_days,
    food_pool_target_for_days,
    pool_query_limit_for_days,
)
from app.modules.place_checker.pool_balancing import CandidatePoolBalancer
from app.modules.place_checker.reranking import CandidateDiversityReranker
from app.modules.place_checker.retrieval_contract import (
    RetrievalBatch,
    RetrievedCandidate,
)
from app.modules.place_checker.scoring_contract import (
    CandidateRankingBatch,
    CandidateScoreComponents,
    ScoredCandidate,
)
from app.modules.place_checker.scoring_policy import SEVERITY_VALUE, hard_violations
from app.modules.place_checker.taxonomy import canonical_label, canonical_labels
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity

WEIGHTS = {
    "intent_match": 0.18,
    "preference_match": 0.12,
    "gap_value": 0.16,
    "budget_fit": 0.12,
    "geo_fit": 0.10,
    "people_fit": 0.08,
    "time_fit": 0.08,
    "quality": 0.05,
    "uniqueness": 0.06,
    "data_confidence": 0.05,
}


class CandidateScoringService:
    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(UTC)

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
        candidates = [
            candidate for gap in retrieval.gaps for candidate in gap.candidates
        ]
        existing_categories, existing_experiences, anchors = self._existing(
            existing_places
        )
        scored = [
            self._score(
                candidate,
                context,
                existing_categories,
                existing_experiences,
                anchors,
            )
            for candidate in candidates
        ]
        ranked = CandidateDiversityReranker().rerank(
            [item for item in scored if item.eligible],
            reserve_limit_per_gap=reserve_limit_per_gap,
        )
        if max_total_candidates is not None:
            existing_count = sum(
                1
                for item in existing_places.places
                if item.place.place_id and item.planner_eligible
            )
            ranked = CandidatePoolBalancer.balance_categories(
                ranked,
                max(0, pool_target - existing_count),
            )
        else:
            ranked = CandidatePoolBalancer.select_entity_type_quotas(
                ranked,
                existing_places,
                activity_target=activity_pool_target_for_days(context.days),
                food_target=food_pool_target_for_days(context.days),
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
        existing_categories: set[str],
        existing_experiences: set[str],
        anchors: list[Coordinates],
    ) -> ScoredCandidate:
        labels = self._labels(candidate)
        category = normalize_text(candidate.category)
        experience = normalize_text(candidate.experience_type)
        distance = self._nearest_distance(candidate.coordinates, anchors)
        components = CandidateScoreComponents(
            intent_match=self._intent_match(candidate, labels),
            preference_match=self._preference_match(context.preferences, labels),
            gap_value=SEVERITY_VALUE[candidate.gap_severity],
            budget_fit=self._budget_fit(candidate, context),
            geo_fit=self._geo_fit(distance),
            people_fit=self._people_fit(candidate, context),
            time_fit=self._time_fit(candidate, context),
            quality=self._quality(candidate),
            uniqueness=(
                1.0
                if category not in existing_categories
                and experience not in existing_experiences
                else 0.35
            ),
            data_confidence=max(item.confidence for item in candidate.evidence),
        )
        component_values = components.model_dump()
        base = sum(WEIGHTS[name] * value for name, value in component_values.items())
        penalties = self._penalties(
            candidate,
            context,
            labels,
            category,
            experience,
            existing_categories,
            existing_experiences,
            distance,
        )
        penalty_total = min(0.65, sum(penalties.values()))
        exclusion_reasons = hard_violations(candidate, context, labels)
        final_score = max(0.0, min(1.0, base - penalty_total))
        return ScoredCandidate(
            candidate=candidate,
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
        labels: set[str],
        category: str,
        experience: str,
        existing_categories: set[str],
        existing_experiences: set[str],
        distance: float | None,
    ) -> dict[str, float]:
        penalties: dict[str, float] = {}
        if self._matches_any(context.avoids, labels):
            penalties["avoid_conflict"] = 0.25
        tier = candidate.metadata.cost_tier if candidate.metadata else CostTier.unknown
        if context.budget.level == "low" and tier in {CostTier.high, CostTier.premium}:
            penalties["high_cost_mismatch"] = 0.15
        if distance is not None and distance > 15:
            penalties["geographic_outlier"] = 0.25
        elif distance is not None and distance > 8:
            penalties["geographic_outlier"] = 0.10
        if category in existing_categories or experience in existing_experiences:
            penalties["duplicate_experience"] = 0.10
        if candidate.verification_status not in {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        }:
            penalties["low_verification"] = 0.20
        if "retrieval:keyword_fallback" in candidate.tags:
            penalties["keyword_fallback"] = 0.08
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

    @classmethod
    def _preference_match(cls, preferences: list[str], labels: set[str]) -> float:
        if not preferences:
            return 0.5
        matches = sum(
            cls._matches_any([preference], labels) for preference in preferences
        )
        return min(1.0, matches / len(preferences))

    @staticmethod
    def _budget_fit(
        candidate: RetrievedCandidate,
        context: TripEvaluationContext,
    ) -> float:
        tier = candidate.metadata.cost_tier if candidate.metadata else CostTier.unknown
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
            ]
            if value
        }

    @staticmethod
    def _matches_any(values: list[str], labels: set[str]) -> bool:
        normalized = canonical_labels(labels)
        return any(canonical_label(value) in normalized for value in values)

    @staticmethod
    def _existing(
        places: PlaceEvaluationBatch,
    ) -> tuple[set[str], set[str], list[Coordinates]]:
        categories: set[str] = set()
        experiences: set[str] = set()
        anchors: list[Coordinates] = []
        for evaluation in places.places:
            if not evaluation.planner_eligible or evaluation.place.metadata is None:
                continue
            metadata = evaluation.place.metadata
            if metadata.category:
                categories.add(normalize_text(metadata.category))
            experiences.update(normalize_text(tag) for tag in metadata.tags if tag)
            if metadata.coordinates:
                anchors.append(metadata.coordinates)
        return categories, experiences, anchors
