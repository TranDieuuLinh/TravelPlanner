from collections.abc import Iterable
from math import log1p

from app.modules.itinerary_planner.contract import PlannerCandidate
from app.shared.tools.bayesian_rating import (
    bayesian_prior,
    bayesian_rating,
    bayesian_review_quality,
)


def bayesian_adjusted_rating_by_id(
    candidates: Iterable[PlannerCandidate],
) -> dict[str, float | None]:
    items = tuple(candidates)
    prior = bayesian_prior(
        (candidate.rating, candidate.review_count) for candidate in items
    )
    return {
        candidate.place_id: bayesian_rating(
            rating=candidate.rating,
            review_count=candidate.review_count,
            prior_mean=prior.mean,
            prior_weight=prior.weight,
        )
        for candidate in items
    }


def bayesian_quality_by_id(
    candidates: Iterable[PlannerCandidate],
) -> dict[str, float]:
    items = tuple(candidates)
    prior = bayesian_prior(
        (candidate.rating, candidate.review_count) for candidate in items
    )
    return {
        candidate.place_id: bayesian_review_quality(
            rating=candidate.rating,
            review_count=candidate.review_count,
            prior=prior,
        ).quality
        for candidate in items
    }


def popularity_by_id(
    candidates: Iterable[PlannerCandidate],
) -> dict[str, float]:
    items = tuple(candidates)
    quality = bayesian_quality_by_id(items)
    max_reviews = max((item.review_count or 0 for item in items), default=0)
    review_scale = log1p(max_reviews) or 1.0
    return {
        item.place_id: (
            0.7 * quality[item.place_id]
            + 0.3 * log1p(max(0, item.review_count or 0)) / review_scale
        )
        for item in items
    }
