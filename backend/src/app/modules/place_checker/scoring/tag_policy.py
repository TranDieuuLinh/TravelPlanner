from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.modules.place_checker.retrieval.contract import RetrievedCandidate


class CandidateTagPolicy:
    """Score only canonical runtime tags declared by tags-auto.yml."""

    @staticmethod
    def candidate_tags(
        candidate: RetrievedCandidate,
        allowed_tags: frozenset[str],
    ) -> tuple[str, ...]:
        metadata_tags = candidate.metadata.tags if candidate.metadata else []
        return tuple(
            dict.fromkeys(
                tag
                for tag in [*candidate.tags, *metadata_tags]
                if tag in allowed_tags
            )
        )

    @staticmethod
    def existing_tags(
        values: Iterable[str],
        allowed_tags: frozenset[str],
    ) -> tuple[str, ...]:
        return tuple(dict.fromkeys(tag for tag in values if tag in allowed_tags))

    @staticmethod
    def filter_intent_tags(
        values: Iterable[str],
        allowed_tags: frozenset[str],
    ) -> list[str]:
        return list(dict.fromkeys(tag for tag in values if tag in allowed_tags))

    @staticmethod
    def preference_ratio(
        preferences: Iterable[str],
        candidate_tags: tuple[str, ...],
    ) -> float:
        if not candidate_tags:
            return 0.0
        preferred = set(preferences)
        matches = sum(tag in preferred for tag in candidate_tags)
        return matches / len(candidate_tags)

    @staticmethod
    def diversity_ratio(
        candidate_tags: tuple[str, ...] | list[str],
        selected_tag_counts: Counter[str],
    ) -> float:
        if not candidate_tags:
            return 0.0
        return sum(
            1 / (1 + selected_tag_counts[tag]) for tag in candidate_tags
        ) / len(candidate_tags)
