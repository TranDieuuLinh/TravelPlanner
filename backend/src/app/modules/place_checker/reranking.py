from app.modules.place_checker.scoring_contract import ScoredCandidate
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km


class CandidateDiversityReranker:
    def rerank(
        self,
        scored: list[ScoredCandidate],
        *,
        reserve_limit_per_gap: int,
    ) -> list[ScoredCandidate]:
        candidates = self._limit_per_gap(
            self._deduplicate(scored),
            reserve_limit_per_gap,
        )
        remaining = list(candidates)
        selected: list[ScoredCandidate] = []
        while remaining:
            rescored = [self._apply_diversity(item, selected) for item in remaining]
            chosen = sorted(
                rescored,
                key=lambda item: (-item.rerank_score, item.candidate.candidate_key),
            )[0]
            selected.append(chosen)
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
    ) -> ScoredCandidate:
        category_repeat = any(
            normalize_text(CandidateDiversityReranker._category_key(chosen))
            == normalize_text(CandidateDiversityReranker._category_key(item))
            for chosen in selected
            if item.candidate.category and chosen.candidate.category
        )
        experience_repeat = any(
            normalize_text(chosen.candidate.experience_type)
            == normalize_text(item.candidate.experience_type)
            for chosen in selected
            if item.candidate.experience_type and chosen.candidate.experience_type
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
        diversity_penalty = (
            0.08 * category_repeat
            + 0.06 * experience_repeat
            + 0.08 * distant_from_selected
        )
        reasons = [
            reason
            for condition, reason in [
                (category_repeat, "repeated_category"),
                (experience_repeat, "repeated_experience"),
                (same_cluster, "same_geographic_cluster"),
                (distant_from_selected, "distant_geographic_cluster"),
            ]
            if condition
        ]
        return item.model_copy(
            update={
                "rerank_score": round(
                    max(0.0, item.final_score - diversity_penalty), 6
                ),
                "rerank_reasons": reasons,
            }
        )

    @staticmethod
    def _category_key(item: ScoredCandidate) -> str:
        return (
            item.candidate.pool_category
            or item.candidate.category
            or "unknown"
        )

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
        groups: dict[str, list[ScoredCandidate]] = {}
        for item in scored:
            groups.setdefault(item.candidate.gap_id, []).append(item)
        return [
            item
            for gap_id in sorted(groups)
            for item in sorted(
                groups[gap_id],
                key=lambda value: (-value.final_score, value.candidate.candidate_key),
            )[:limit]
        ]
