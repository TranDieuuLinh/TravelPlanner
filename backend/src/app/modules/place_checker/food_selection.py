from __future__ import annotations

from collections import defaultdict
from math import ceil

from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import OperationalStatus
from app.modules.place_checker.food_selection_contract import (
    FoodRestaurantCandidate,
    FoodSelectionAnchor,
    FoodSelectionBatch,
    SelectedFoodRestaurant,
)
from app.modules.place_checker.food_meal_matching import (
    build_food_meal_coverage,
    matched_restaurant_ids,
    missing_meals,
)
from app.modules.place_checker.food_pool_policy import (
    MAX_FOOD_POOL,
    MEALS,
    RestaurantAggregate,
    aggregate_restaurants,
    select_food_pool,
)
from app.modules.place_checker.planning_time_windows import (
    meals_for_hours,
    parse_planner_windows,
)
from app.modules.place_checker.ports import SpecialFoodRestaurantSource
from app.modules.place_checker.price_policy import has_usable_cost
from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
    bayesian_prior,
    bayesian_rating,
    bayesian_review_quality,
)


class FoodRestaurantSelectionService:
    """Build a validated, quota-driven food pool around travel anchors."""

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
        hard_target = min(MAX_FOOD_POOL, context.days * len(MEALS))
        per_anchor_limit = min(
            12,
            max(4, ceil(hard_target * 1.3 / max(1, len(anchors)))),
        )
        try:
            candidates = await self.source.find_food_restaurants(
                adm_id=adm_id,
                anchor_place_ids=[anchor.place_id for anchor in anchors],
                radius_km=5.0,
                per_anchor_limit=per_anchor_limit,
                excluded_restaurant_ids=[],
                required_meals=[],
            )
        except Exception:
            return FoodSelectionBatch(
                unmatched_anchor_place_ids=[anchor.place_id for anchor in anchors],
                warnings=[
                    "Không thể lấy quán ăn phù hợp gần các điểm tham quan."
                ],
            )

        rejected: dict[str, int] = defaultdict(int)
        eligible: list[FoodRestaurantCandidate] = []
        for candidate in self._deduplicate(candidates, context):
            reason = self._ineligible_reason(candidate, context)
            if reason is not None:
                rejected[reason] += 1
                continue
            eligible.append(candidate)
        priors = self._priors(eligible)
        aggregates = aggregate_restaurants(eligible, priors, self._rank)
        meal_coverage = build_food_meal_coverage(
            aggregates,
            context.days,
            lambda item: self._rank(item.best, priors),
        )
        reserve_deficit = len(meal_coverage.hard_missing_slots) + len(
            meal_coverage.reserve_missing_slots
        )
        if reserve_deficit:
            excluded_ids = list(
                dict.fromkeys(item.restaurant_id for item in candidates)
            )
            try:
                general = await self.source.find_food_restaurants(
                    adm_id=adm_id,
                    anchor_place_ids=[anchor.place_id for anchor in anchors],
                    radius_km=None,
                    per_anchor_limit=min(
                        12,
                        max(3, ceil(reserve_deficit * 1.3)),
                    ),
                    excluded_restaurant_ids=excluded_ids,
                    required_meals=missing_meals(meal_coverage),
                )
            except Exception:
                general = []
            for candidate in self._deduplicate(general, context):
                reason = self._ineligible_reason(candidate, context)
                if reason is not None:
                    rejected[reason] += 1
                else:
                    eligible.append(candidate)
            priors = self._priors(eligible)
            aggregates = aggregate_restaurants(eligible, priors, self._rank)
            meal_coverage = build_food_meal_coverage(
                aggregates,
                context.days,
                lambda item: self._rank(item.best, priors),
            )

        selected_pool = select_food_pool(
            aggregates,
            context.days,
            priors,
            self._rank,
            required_ids=matched_restaurant_ids(meal_coverage),
        )
        anchor_names = {anchor.place_id: anchor.name for anchor in anchors}
        selections = [
            self._to_selection(item, anchor_names, priors)
            for item in selected_pool
        ]
        matched = {
            anchor_id
            for item in aggregates
            for anchor_id in item.related_anchor_ids
        }
        unmatched = [anchor.place_id for anchor in anchors if anchor.place_id not in matched]
        warnings = [
            *(
                [
                    f"Không tìm thấy quán phù hợp gần {len(unmatched)} "
                    "điểm tham quan."
                ]
                if unmatched
                else []
            ),
            *(
                [
                    "Đã loại candidate quán không đủ dữ liệu trước selection: "
                    + ", ".join(
                        f"{reason}={count}" for reason, count in sorted(rejected.items())
                    )
                    + "."
                ]
                if rejected
                else []
            ),
            *(
                [
                    "Food meal matching không đủ hard coverage: "
                    f"hard_missing={len(meal_coverage.hard_missing_slots)}, "
                    f"reserve_missing={len(meal_coverage.reserve_missing_slots)}."
                ]
                if meal_coverage.hard_missing_slots
                else []
            ),
        ]
        return FoodSelectionBatch(
            selections=selections,
            unmatched_anchor_place_ids=unmatched,
            warnings=warnings,
            meal_coverage=meal_coverage,
        )

    def _to_selection(
        self,
        aggregate: RestaurantAggregate,
        anchor_names: dict[str, str],
        priors: dict[str, BayesianRatingPrior],
    ) -> SelectedFoodRestaurant:
        selected = aggregate.best
        bayesian = self._bayesian(selected, priors)
        reason = (
            "sole_candidate_for_food"
            if aggregate.food_peer_count == 1
            else "bayesian_ranked"
            if bayesian is not None
            else "quality_fallback"
        )
        return SelectedFoodRestaurant(
            anchor_place_id=selected.anchor_place_id,
            anchor_name=anchor_names.get(selected.anchor_place_id, "khu vực lịch trình"),
            related_anchor_place_ids=list(aggregate.related_anchor_ids),
            food_item_id=selected.food_item_id,
            food_item_name=selected.food_item_name,
            offered_food_item_id=selected.offered_food_item_id,
            offered_food_item_name=selected.offered_food_item_name,
            food_match_type=selected.food_match_type,
            food_match_confidence=selected.food_match_confidence,
            restaurant_id=selected.restaurant_id,
            restaurant_name=selected.restaurant_name,
            distance_km=selected.distance_km,
            rating=selected.metadata.rating,
            review_count=selected.metadata.review_count,
            bayesian_rating=bayesian,
            pair_score=self._pair_score(selected, priors),
            selection_reason=reason,
            proximity_source=selected.proximity_source,
            evidence_types=list(aggregate.evidence_types),
            metadata=selected.metadata,
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

    @classmethod
    def _deduplicate(
        cls,
        candidates: list[FoodRestaurantCandidate],
        context: TripEvaluationContext,
    ) -> list[FoodRestaurantCandidate]:
        """Keep one restaurant option per anchor without losing anchor coverage."""
        selected: dict[tuple[str, str], FoodRestaurantCandidate] = {}
        for candidate in candidates:
            key = (candidate.anchor_place_id, candidate.restaurant_id)
            current = selected.get(key)
            if current is None or cls._dedupe_rank(
                candidate, context
            ) > cls._dedupe_rank(current, context):
                selected[key] = candidate
        return list(selected.values())

    @classmethod
    def _dedupe_rank(
        cls,
        candidate: FoodRestaurantCandidate,
        context: TripEvaluationContext,
    ) -> tuple[int, int, float, float, float, int, str]:
        return (
            int(cls._ineligible_reason(candidate, context) is None),
            int(candidate.food_match_type == "direct_id"),
            candidate.food_priority,
            candidate.food_confidence,
            candidate.offer_confidence,
            candidate.metadata.review_count or 0,
            candidate.food_item_id,
        )

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
    def _ineligible_reason(
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
