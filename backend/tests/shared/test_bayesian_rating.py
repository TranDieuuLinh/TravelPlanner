from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
    bayesian_prior,
    bayesian_rating,
    bayesian_review_quality,
)


def test_prior_uses_rating_mean_and_median_review_weight() -> None:
    prior = bayesian_prior([(4.0, 10), (5.0, 100)], minimum_weight=20)

    assert prior == BayesianRatingPrior(mean=4.5, weight=55)


def test_sparse_rating_is_shrunk_but_not_rejected() -> None:
    score = bayesian_rating(
        rating=5,
        review_count=1,
        prior_mean=4.2,
        prior_weight=20,
    )

    assert score == 4.238095


def test_review_quality_rewards_reliability() -> None:
    prior = BayesianRatingPrior(mean=4.2, weight=20)
    reliable = bayesian_review_quality(
        rating=4.8,
        review_count=2_000,
        prior=prior,
    )
    sparse = bayesian_review_quality(
        rating=5,
        review_count=1,
        prior=prior,
    )

    assert reliable.quality > sparse.quality
    assert reliable.reliability > sparse.reliability
