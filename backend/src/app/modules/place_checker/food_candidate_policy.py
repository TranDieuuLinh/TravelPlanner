from __future__ import annotations

from collections import defaultdict

from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import OperationalStatus
from app.modules.place_checker.food_selection_contract import FoodRestaurantCandidate
from app.modules.place_checker.planning_time_windows import (
    meals_for_hours,
    parse_planner_windows,
)
from app.modules.place_checker.price_policy import has_usable_cost
from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
    bayesian_prior,
    bayesian_rating,
    bayesian_review_quality,
)


class FoodCandidatePolicy:
    def __init__(self, *, minimum_prior_reviews: int = 20) -> None:
        self.minimum_prior_reviews = max(0, minimum_prior_reviews)

    def priors(
        self, candidates: list[FoodRestaurantCandidate]
    ) -> dict[str, BayesianRatingPrior]:
        observations: dict[str, list[tuple[float | None, int | None]]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            key = (candidate.food_item_id, candidate.restaurant_id)
            if candidate.metadata.rating is None or key in seen:
                continue
            seen.add(key)
            observations[candidate.food_item_id].append(
                (candidate.metadata.rating, candidate.metadata.review_count)
            )
        return {
            food_item_id: bayesian_prior(
                values,
                minimum_weight=self.minimum_prior_reviews,
            )
            for food_item_id, values in observations.items()
        }

    def bayesian(
        self,
        candidate: FoodRestaurantCandidate,
        priors: dict[str, BayesianRatingPrior],
    ) -> float | None:
        prior = priors.get(
            candidate.food_item_id,
            BayesianRatingPrior(None, float(self.minimum_prior_reviews)),
        )
        return bayesian_rating(
            rating=candidate.metadata.rating,
            review_count=candidate.metadata.review_count,
            prior_mean=prior.mean,
            prior_weight=prior.weight,
        )

    def rank(
        self,
        candidate: FoodRestaurantCandidate,
        priors: dict[str, BayesianRatingPrior],
    ) -> tuple[float, float, float, int, str]:
        return (
            self.pair_score(candidate, priors),
            self.bayesian(candidate, priors) or 0.0,
            -(candidate.distance_km if candidate.distance_km is not None else 999.0),
            candidate.metadata.review_count or 0,
            candidate.restaurant_id,
        )

    def pair_score(
        self,
        candidate: FoodRestaurantCandidate,
        priors: dict[str, BayesianRatingPrior],
    ) -> float:
        prior = priors.get(
            candidate.food_item_id,
            BayesianRatingPrior(None, float(self.minimum_prior_reviews)),
        )
        quality = bayesian_review_quality(
            rating=candidate.metadata.rating,
            review_count=candidate.metadata.review_count,
            prior=prior,
        ).quality
        proximity = self._proximity(candidate)
        value = (
            0.35 * candidate.food_priority
            + 0.10 * candidate.food_confidence
            + 0.10 * candidate.offer_confidence
            + 0.10 * candidate.food_match_confidence
            + 0.25 * quality
            + 0.10 * proximity
        )
        return round(min(1.0, max(0.0, value)), 6)

    @staticmethod
    def _proximity(candidate: FoodRestaurantCandidate) -> float:
        if candidate.distance_km is None:
            return 0.4
        threshold = candidate.threshold_km or 2.0
        return max(0.0, 1.0 - candidate.distance_km / threshold)

    @staticmethod
    def ineligible_reason(
        candidate: FoodRestaurantCandidate,
        context: TripEvaluationContext,
    ) -> str | None:
        metadata = candidate.metadata
        if metadata.operational_status == OperationalStatus.permanently_closed:
            return "permanently_closed"
        if context.people.children and metadata.children_suitable is False:
            return "children_unsuitable"
        if context.people.infants and metadata.infants_suitable is False:
            return "infants_unsuitable"
        if has_avoid_conflict(
            context.avoids,
            [
                candidate.food_item_name,
                candidate.restaurant_name,
                metadata.category or "",
                *metadata.tags,
            ],
        ):
            return "avoid_conflict"
        if metadata.coordinates is None:
            return "missing_coordinates"
        if metadata.typical_duration_minutes is None:
            return "missing_duration"
        if not has_usable_cost(
            minimum=metadata.minimum_cost,
            typical=metadata.typical_cost,
            maximum=metadata.maximum_cost,
            tier=metadata.cost_tier,
        ):
            return "missing_cost"
        if not metadata.opening_hours or not parse_planner_windows(
            metadata.opening_hours
        ):
            return "missing_meal_window"
        if not meals_for_hours(metadata.opening_hours):
            return "unsupported_meal_window"
        return None
