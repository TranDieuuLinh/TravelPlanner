from collections import Counter

from app.modules.place_checker.planning.category import planner_category_for_candidate
from app.modules.place_checker.scoring.contract import ScoredCandidate
from app.modules.place_checker.scoring.tag_policy import CandidateTagPolicy
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km


class CandidateDiversityReranker:
    TAG_DIVERSITY_WEIGHT = 0.05

    def rerank(
        self,
        scored: list[ScoredCandidate],
        *,
        reserve_limit_per_gap: int,
        initial_tag_counts: Counter[str] | None = None,
    ) -> list[ScoredCandidate]:
        candidates = self._limit_per_gap(
            self._deduplicate(scored),
            reserve_limit_per_gap,
        )
        remaining = list(candidates)
        selected: list[ScoredCandidate] = []
        selected_tag_counts = Counter(initial_tag_counts or {})
        while remaining:
            rescored = [
                self._apply_diversity(item, selected, selected_tag_counts)
                for item in remaining
            ]
            chosen = min(
                rescored,
                key=lambda item: (-item.rerank_score, item.candidate.candidate_key),
            )
            selected.append(chosen)
            if self._uses_tag_diversity(chosen):
                selected_tag_counts.update(chosen.selection_tags)
            remaining = [
                item
                for item in remaining
                if item.candidate.candidate_key != chosen.candidate.candidate_key
            ]
        return [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(selected, start=1)
        ]

    @staticmethod
    def _apply_diversity(
        item: ScoredCandidate,
        selected: list[ScoredCandidate],
        selected_tag_counts: Counter[str],
    ) -> ScoredCandidate:
        uses_tag_diversity = CandidateDiversityReranker._uses_tag_diversity(item)
        diversity_ratio = (
            CandidateTagPolicy.diversity_ratio(
                item.selection_tags,
                selected_tag_counts,
            )
            if uses_tag_diversity
            else 0.0
        )
        known_distances = [
            distance_km(chosen.candidate.coordinates, item.candidate.coordinates)
            for chosen in selected
            if chosen.candidate.coordinates and item.candidate.coordinates
        ]
        distant_from_selected = bool(known_distances) and min(known_distances) > 8
        same_cluster = any(
            chosen.candidate.coordinates
            and item.candidate.coordinates
            and distance_km(
                chosen.candidate.coordinates,
                item.candidate.coordinates,
            ) <= 2
            for chosen in selected
        )
        distance_penalty = 0.08 * distant_from_selected
        diversity_bonus = CandidateDiversityReranker.TAG_DIVERSITY_WEIGHT * (
            diversity_ratio
        )
        adjusted_components = item.components.model_copy(
            update={"uniqueness": diversity_ratio}
        )
        adjusted_base = min(1.0, item.base_score + diversity_bonus)
        adjusted_final = max(0.0, adjusted_base - item.penalty_total)
        reasons = [
            reason
            for condition, reason in [
                (
                    uses_tag_diversity
                    and any(selected_tag_counts[tag] == 0 for tag in item.selection_tags),
                    "new_canonical_tag",
                ),
                (
                    uses_tag_diversity
                    and any(selected_tag_counts[tag] > 0 for tag in item.selection_tags),
                    "repeated_canonical_tag",
                ),
                (same_cluster, "same_geographic_cluster"),
                (distant_from_selected, "distant_geographic_cluster"),
            ]
            if condition
        ]
        return item.model_copy(
            update={
                "components": adjusted_components,
                "base_score": round(adjusted_base, 6),
                "final_score": round(adjusted_final, 6),
                "rerank_score": round(
                    max(0.0, adjusted_final - distance_penalty), 6
                ),
                "tag_diversity_score": round(diversity_ratio, 6),
                "rerank_reasons": reasons,
            }
        )

    @staticmethod
    def _uses_tag_diversity(item: ScoredCandidate) -> bool:
        return bool(item.selection_tags) and planner_category_for_candidate(
            item.candidate.category,
            name=item.candidate.canonical_name,
            tags=item.candidate.tags,
            pool_category=item.candidate.pool_category,
        ) == "travel_place"

    @staticmethod
    def _deduplicate(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
        selected: dict[str, ScoredCandidate] = {}
        for item in scored:
            current = selected.get(item.candidate.candidate_key)
            if current is None or item.final_score > current.final_score:
                selected[item.candidate.candidate_key] = item
        return list(selected.values())

    @staticmethod
    def _limit_per_gap(
        scored: list[ScoredCandidate],
        limit: int,
    ) -> list[ScoredCandidate]:
        groups: dict[tuple[str, str], list[ScoredCandidate]] = {}
        for item in scored:
            category = normalize_text(item.candidate.category) or "unknown"
            groups.setdefault((item.candidate.gap_id, category), []).append(item)
        return [
            item
            for group_key in sorted(groups)
            for item in sorted(
                groups[group_key],
                key=lambda value: (-value.final_score, value.candidate.candidate_key),
            )[:limit]
        ]
