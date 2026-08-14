from dataclasses import dataclass
from statistics import median
from typing import Iterable


RatingObservation = tuple[float | None, int | None]


@dataclass(frozen=True, slots=True)
class BayesianRatingPrior:
    mean: float | None
    weight: float


@dataclass(frozen=True, slots=True)
class BayesianReviewQuality:
    adjusted_rating: float | None
    reliability: float
    quality: float


def bayesian_prior(
    observations: Iterable[RatingObservation],
    *,
    minimum_weight: float = 20,
) -> BayesianRatingPrior:
    values = [
        (rating, max(0, reviews or 0))
        for rating, reviews in observations
        if rating is not None
    ]
    if not values:
        return BayesianRatingPrior(mean=None, weight=max(0.0, minimum_weight))
    return BayesianRatingPrior(
        mean=sum(rating for rating, _ in values) / len(values),
        weight=max(
            0.0,
            minimum_weight,
            float(median(reviews for _, reviews in values)),
        ),
    )


def bayesian_rating(
    *,
    rating: float | None,
    review_count: int | None,
    prior_mean: float | None,
    prior_weight: float,
) -> float | None:
    """Return a bounded weighted mean without rejecting sparse candidates."""
    if rating is None:
        return None
    if prior_mean is None:
        return rating
    reviews = max(0, review_count or 0)
    weight = max(0.0, prior_weight)
    if reviews + weight == 0:
        return rating
    score = (reviews * rating + weight * prior_mean) / (reviews + weight)
    return round(min(5.0, max(0.0, score)), 6)


def bayesian_review_quality(
    *,
    rating: float | None,
    review_count: int | None,
    prior: BayesianRatingPrior,
    max_rating: float = 5,
    reliability_floor: float = 0.70,
) -> BayesianReviewQuality:
    adjusted = bayesian_rating(
        rating=rating,
        review_count=review_count,
        prior_mean=prior.mean,
        prior_weight=prior.weight,
    )
    reviews = max(0, review_count or 0)
    reliability = (
        reviews / (reviews + prior.weight)
        if reviews + prior.weight
        else 0.0
    )
    floor = min(1.0, max(0.0, reliability_floor))
    quality = 0.0
    if adjusted is not None and max_rating > 0:
        quality = (adjusted / max_rating) * (
            floor + (1 - floor) * reliability
        )
    return BayesianReviewQuality(
        adjusted_rating=adjusted,
        reliability=round(reliability, 6),
        quality=round(min(1.0, max(0.0, quality)), 6),
    )
