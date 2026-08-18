from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from app.modules.place_checker.planner_category import planner_category
from app.modules.place_checker.planner_category import planner_category_for_candidate
from app.modules.place_checker.retrieval_contract import RetrievedCandidate
from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
    bayesian_prior,
    bayesian_review_quality,
)


# Rating/review signals are deliberately strongest for TravelPlace. Restaurants
# often have much larger review volumes, so their raw counts must not dominate
# the activity reserve. DrinkDessert and Entertainment are optional signals.
CATEGORY_REPUTATION_FACTORS: dict[str, tuple[float, float]] = {
    "travel_place": (1.00, 1.00),
    "restaurant": (0.70, 0.40),
    "drink_dessert": (0.20, 0.08),
    "entertainment": (0.20, 0.08),
    "default": (0.50, 0.25),
}


@dataclass(frozen=True, slots=True)
class CategoryReputationProfile:
    prior: BayesianRatingPrior
    max_reviews: int
    rating_factor: float
    review_factor: float


def build_reputation_profiles(
    candidates: list[RetrievedCandidate],
) -> dict[str, CategoryReputationProfile]:
    observations: dict[str, list[tuple[float | None, int | None]]] = {}
    for candidate in candidates:
        metadata = candidate.metadata
        category = planner_category_for_candidate(
            candidate.category,
            name=candidate.canonical_name,
            tags=candidate.tags,
            pool_category=candidate.pool_category,
        )
        observations.setdefault(category, []).append(
            (
                metadata.rating if metadata else None,
                metadata.review_count if metadata else None,
            )
        )

    profiles: dict[str, CategoryReputationProfile] = {}
    for category, values in observations.items():
        rating_factor, review_factor = CATEGORY_REPUTATION_FACTORS.get(
            category,
            CATEGORY_REPUTATION_FACTORS["default"],
        )
        profiles[category] = CategoryReputationProfile(
            prior=bayesian_prior(values),
            max_reviews=max((reviews or 0 for _, reviews in values), default=0),
            rating_factor=rating_factor,
            review_factor=review_factor,
        )
    return profiles


def reputation_components(
    candidate: RetrievedCandidate,
    profiles: dict[str, CategoryReputationProfile],
) -> tuple[float, float]:
    metadata = candidate.metadata
    profile = profiles.get(
        planner_category_for_candidate(
            candidate.category,
            name=candidate.canonical_name,
            tags=candidate.tags,
            pool_category=candidate.pool_category,
        )
    )
    if metadata is None or profile is None:
        return 0.0, 0.0

    quality = bayesian_review_quality(
        rating=metadata.rating,
        review_count=metadata.review_count,
        prior=profile.prior,
    )
    rating_signal = (
        quality.adjusted_rating / 5.0
        if quality.adjusted_rating is not None
        else 0.0
    )
    reviews = max(0, metadata.review_count or 0)
    review_signal = (
        log1p(reviews) / log1p(profile.max_reviews)
        if profile.max_reviews
        else 0.0
    )
    return (
        round(rating_signal * profile.rating_factor, 6),
        round(review_signal * profile.review_factor, 6),
    )
