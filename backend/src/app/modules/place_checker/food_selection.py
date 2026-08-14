from __future__ import annotations

from collections import defaultdict

from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import OperationalStatus
from app.modules.place_checker.food_selection_contract import (
    FoodRestaurantCandidate,
    FoodSelectionAnchor,
    FoodSelectionBatch,
    SelectedFoodRestaurant,
)
from app.modules.place_checker.ports import SpecialFoodRestaurantSource
from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
    bayesian_prior,
    bayesian_rating,
    bayesian_review_quality,
)


class FoodRestaurantSelectionService:
    """Select one destination-special food venue for every travel-place anchor."""

    def __init__(
        self,
        source: SpecialFoodRestaurantSource,
        *,
        minimum_prior_reviews: int = 20,
    ) -> None:
        self.source = source
        self.minimum_prior_reviews = max(0, minimum_prior_reviews)

    async def select(
        self,
        context: TripEvaluationContext,
        anchors: list[FoodSelectionAnchor],
    ) -> FoodSelectionBatch:
        adm_id = context.destination.adm_id
        if not adm_id or not anchors:
            return FoodSelectionBatch()
        try:
            candidates = await self.source.find_food_restaurants(
                adm_id=adm_id,
                anchor_place_ids=[anchor.place_id for anchor in anchors],
            )
        except Exception:
            return FoodSelectionBatch(
                unmatched_anchor_place_ids=[anchor.place_id for anchor in anchors],
                warnings=[
                    "Không thể lấy quán ăn đặc trưng gần các điểm tham quan."
                ],
            )

        eligible = [
            candidate
            for candidate in candidates
            if self._eligible(candidate, context)
        ]
        priors = self._priors(eligible)
        grouped: dict[str, list[FoodRestaurantCandidate]] = defaultdict(list)
        for candidate in eligible:
            grouped[candidate.anchor_place_id].append(candidate)

        selections: list[SelectedFoodRestaurant] = []
        unmatched: list[str] = []
        used_restaurants: set[str] = set()
        for anchor in anchors:
            options = grouped.get(anchor.place_id, [])
            if not options:
                unmatched.append(anchor.place_id)
                continue
            unused = [
                option
                for option in options
                if option.restaurant_id not in used_restaurants
            ]
            ranked_pool = unused or options
            selected = max(
                ranked_pool,
                key=lambda option: self._rank(option, priors),
            )
            same_food = [
                option
                for option in options
                if option.food_item_id == selected.food_item_id
            ]
            bayesian = self._bayesian(selected, priors)
            if len(same_food) == 1:
                reason = "sole_candidate_for_food"
            elif bayesian is not None:
                reason = "bayesian_ranked"
            else:
                reason = "quality_fallback"
            selections.append(
                SelectedFoodRestaurant(
                    anchor_place_id=anchor.place_id,
                    anchor_name=anchor.name,
                    food_item_id=selected.food_item_id,
                    food_item_name=selected.food_item_name,
                    restaurant_id=selected.restaurant_id,
                    restaurant_name=selected.restaurant_name,
                    distance_km=selected.distance_km,
                    rating=selected.metadata.rating,
                    review_count=selected.metadata.review_count,
                    bayesian_rating=bayesian,
                    pair_score=self._pair_score(selected, priors),
                    selection_reason=reason,
                    metadata=selected.metadata,
                )
            )
            used_restaurants.add(selected.restaurant_id)
        warnings = (
            [
                f"Không tìm thấy quán đặc trưng gần {len(unmatched)} "
                "điểm tham quan."
            ]
            if unmatched
            else []
        )
        return FoodSelectionBatch(
            selections=selections,
            unmatched_anchor_place_ids=unmatched,
            warnings=warnings,
        )

    def _priors(
        self,
        candidates: list[FoodRestaurantCandidate],
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

    def _bayesian(
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

    def _rank(
        self,
        candidate: FoodRestaurantCandidate,
        priors: dict[str, BayesianRatingPrior],
    ) -> tuple[float, float, float, int, str]:
        return (
            self._pair_score(candidate, priors),
            self._bayesian(candidate, priors) or 0.0,
            -(candidate.distance_km if candidate.distance_km is not None else 999.0),
            candidate.metadata.review_count or 0,
            candidate.restaurant_id,
        )

    def _pair_score(
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
            0.40 * candidate.food_priority
            + 0.10 * candidate.food_confidence
            + 0.10 * candidate.offer_confidence
            + 0.30 * quality
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
    def _eligible(
        candidate: FoodRestaurantCandidate,
        context: TripEvaluationContext,
    ) -> bool:
        metadata = candidate.metadata
        if metadata.operational_status == OperationalStatus.permanently_closed:
            return False
        if context.people.children and metadata.children_suitable is False:
            return False
        if context.people.infants and metadata.infants_suitable is False:
            return False
        return not has_avoid_conflict(
            context.avoids,
            [
                candidate.food_item_name,
                candidate.restaurant_name,
                metadata.category or "",
                *metadata.tags,
            ],
        )
