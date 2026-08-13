from collections.abc import Iterable

from app.modules.place_checker.taxonomy import canonical_label, canonical_labels


def matching_avoids(avoids: Iterable[str], candidate_labels: Iterable[str]) -> list[str]:
    """Return original avoid values matched through the canonical taxonomy."""
    normalized_candidates = canonical_labels(set(candidate_labels))
    return [
        avoid
        for avoid in avoids
        if canonical_label(avoid) in normalized_candidates
    ]


def has_avoid_conflict(
    avoids: Iterable[str],
    candidate_labels: Iterable[str],
) -> bool:
    return bool(matching_avoids(avoids, candidate_labels))
