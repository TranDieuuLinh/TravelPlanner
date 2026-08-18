from __future__ import annotations

from collections import Counter
from math import ceil, log1p

from app.modules.place_checker.planner_candidate_metadata import source_metadata
from app.modules.place_checker.scoring_contract import ScoredCandidate
from app.shared.tools.bayesian_rating import (
    bayesian_prior,
    bayesian_review_quality,
)

COMPOSITION_BASE = 14
SPECIAL_SLOTS = 8
POPULAR_SLOTS = 4
MAX_DIVERSITY_TAG_OCCURRENCES = 3
MIN_POPULAR_REVIEW_COUNT = 500
MIN_POPULARITY_SCORE = 0.70
NON_DIVERSITY_TAG_PREFIXES = (
    "item:",
    "pool_category:",
    "relationship:",
    "retrieval:",
    "style:",
)
NON_DIVERSITY_TAGS = frozenset(
    {"experience:special_experience", "travel place", "travel_place"}
)


def select_activity_coverage(
    ranked: list[ScoredCandidate],
    limit: int,
) -> list[ScoredCandidate]:
    """Build a diverse reserve; final itinerary selection remains in Planner."""
    if limit <= 0:
        return []
    if len(ranked) <= limit:
        return _with_ranks(ranked)

    special_target = ceil(limit * SPECIAL_SLOTS / COMPOSITION_BASE)
    popular_target = ceil(limit * POPULAR_SLOTS / COMPOSITION_BASE)
    selected: list[ScoredCandidate] = []
    selected_keys: set[str] = set()

    _take_tag_coverage(selected, selected_keys, ranked, limit)

    special = [item for item in ranked if _is_special(item)]
    selected_special = sum(_is_special(item) for item in selected)
    _take(
        selected,
        selected_keys,
        special,
        max(0, special_target - selected_special),
    )

    popularity = _popularity_scores(ranked)
    popular = sorted(
        (
            item
            for item in ranked
            if item.candidate.candidate_key not in selected_keys
            and _is_popular(
                item,
                popularity[item.candidate.candidate_key],
            )
        ),
        key=lambda item: (
            -popularity[item.candidate.candidate_key],
            item.candidate.candidate_key,
        ),
    )
    selected_popular = sum(
        _is_popular(item, popularity[item.candidate.candidate_key])
        for item in selected
    )
    _take(
        selected,
        selected_keys,
        popular,
        max(0, popular_target - selected_popular),
    )
    _take_diverse_fill(
        selected,
        selected_keys,
        ranked,
        limit - len(selected),
    )
    return _with_ranks(selected)


def _take_tag_coverage(
    selected: list[ScoredCandidate],
    selected_keys: set[str],
    ranked: list[ScoredCandidate],
    limit: int,
) -> None:
    """Reserve one candidate per meaningful KG tag before score-only fill."""
    groups: dict[str, list[ScoredCandidate]] = {}
    for item in ranked:
        for tag in _diversity_tags(item):
            groups.setdefault(tag, []).append(item)
    ordered_groups = sorted(
        groups,
        key=lambda group: (
            -groups[group][0].rerank_score,
            group,
        ),
    )
    for group in ordered_groups:
        if len(selected) >= limit:
            break
        if any(
            item.candidate.candidate_key in selected_keys
            for item in groups[group]
        ):
            continue
        _take(selected, selected_keys, groups[group], 1)


def _diversity_tags(item: ScoredCandidate) -> set[str]:
    candidate = item.candidate
    tags = [
        *candidate.tags,
        *(candidate.metadata.tags if candidate.metadata else []),
    ]
    normalized = {
        tag.strip().casefold()
        for tag in tags
        if tag.strip()
        and tag.strip().casefold() not in NON_DIVERSITY_TAGS
        and not tag.strip().casefold().startswith(NON_DIVERSITY_TAG_PREFIXES)
    }
    return normalized or {(candidate.category or "unknown").casefold()}


def _take(
    selected: list[ScoredCandidate],
    selected_keys: set[str],
    candidates: list[ScoredCandidate],
    count: int,
) -> None:
    added = 0
    for item in candidates:
        if added >= count:
            break
        key = item.candidate.candidate_key
        if key in selected_keys:
            continue
        selected.append(item)
        selected_keys.add(key)
        added += 1


def _take_diverse_fill(
    selected: list[ScoredCandidate],
    selected_keys: set[str],
    candidates: list[ScoredCandidate],
    count: int,
) -> None:
    """Fill the reserve while soft-capping repeated broad tags."""
    if count <= 0:
        return

    tag_counts = Counter(
        tag
        for item in selected
        for tag in _diversity_tags(item)
    )
    remaining = [
        item
        for item in candidates
        if item.candidate.candidate_key not in selected_keys
    ]
    for _ in range(count):
        if not remaining:
            break
        eligible = [
            item
            for item in remaining
            if not any(
                tag_counts[tag] >= MAX_DIVERSITY_TAG_OCCURRENCES
                for tag in _diversity_tags(item)
            )
        ]
        pool = eligible or remaining
        chosen = min(pool, key=lambda item: _diversity_fill_key(item, tag_counts))
        selected.append(chosen)
        selected_keys.add(chosen.candidate.candidate_key)
        tag_counts.update(_diversity_tags(chosen))
        remaining.remove(chosen)


def _diversity_fill_key(
    item: ScoredCandidate,
    tag_counts: Counter[str],
) -> tuple[float, int, float, str]:
    tags = _diversity_tags(item)
    return (
        sum(tag_counts[tag] for tag in tags),
        max((tag_counts[tag] for tag in tags), default=0),
        -item.rerank_score,
        item.candidate.candidate_key,
    )


def _is_special(item: ScoredCandidate) -> bool:
    metadata_relationships = (
        item.candidate.metadata.relationships if item.candidate.metadata else []
    )
    source_kind, _ = source_metadata(
        [*item.candidate.relationships, *metadata_relationships],
        [
            *item.candidate.tags,
            f"pool_category:{item.candidate.pool_category or ''}",
        ],
    )
    return source_kind in {"special_experience", "both"}


def _is_popular(item: ScoredCandidate, popularity_score: float) -> bool:
    metadata = item.candidate.metadata
    return bool(
        metadata
        and metadata.rating is not None
        and (metadata.review_count or 0) >= MIN_POPULAR_REVIEW_COUNT
        and popularity_score >= MIN_POPULARITY_SCORE
    )


def _popularity_scores(ranked: list[ScoredCandidate]) -> dict[str, float]:
    observations = [
        (
            item.candidate.metadata.rating if item.candidate.metadata else None,
            item.candidate.metadata.review_count if item.candidate.metadata else None,
        )
        for item in ranked
    ]
    prior = bayesian_prior(observations)
    max_reviews = max((reviews or 0 for _, reviews in observations), default=0)
    review_scale = log1p(max_reviews) or 1.0
    scores: dict[str, float] = {}
    for item in ranked:
        metadata = item.candidate.metadata
        rating = metadata.rating if metadata else None
        reviews = metadata.review_count if metadata else None
        quality = bayesian_review_quality(
            rating=rating,
            review_count=reviews,
            prior=prior,
        ).quality
        review_signal = log1p(max(0, reviews or 0)) / review_scale
        scores[item.candidate.candidate_key] = 0.7 * quality + 0.3 * review_signal
    return scores


def _with_ranks(items: list[ScoredCandidate]) -> list[ScoredCandidate]:
    return [
        item.model_copy(update={"rank": index})
        for index, item in enumerate(items, start=1)
    ]
