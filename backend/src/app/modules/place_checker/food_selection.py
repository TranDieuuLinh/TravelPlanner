from __future__ import annotations

from collections import defaultdict
from math import ceil

from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.food_candidate_policy import FoodCandidatePolicy
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
from app.modules.place_checker.food_item_diversity import (
    coverage_shortfall,
    select_style_item_candidates,
)
from app.modules.place_checker.food_pool_policy import (
    MAX_FOOD_POOL,
    MEALS,
    RestaurantAggregate,
    aggregate_restaurants,
    select_food_pool,
)
from app.modules.place_checker.ports import SpecialFoodRestaurantSource
from app.shared.tools.bayesian_rating import (
    BayesianRatingPrior,
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
        self.policy = FoodCandidatePolicy(
            minimum_prior_reviews=self.minimum_prior_reviews
        )

    async def select(
        self,
        context: TripEvaluationContext,
        anchors: list[FoodSelectionAnchor],
        *,
        active_style_ids: set[str] | None = None,
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
            reason = self.policy.ineligible_reason(candidate, context)
            if reason is not None:
                rejected[reason] += 1
                continue
            eligible.append(candidate)
        priors = self.policy.priors(eligible)
        diverse, style_coverage = select_style_item_candidates(
            eligible,
            context.days,
            priors,
            self.policy.rank,
            active_style_ids=active_style_ids,
        )
        preferred = {item.restaurant_id: item for item in diverse}
        aggregates = aggregate_restaurants(
            eligible,
            priors,
            self.policy.rank,
            preferred_by_restaurant=preferred,
        )
        meal_coverage = build_food_meal_coverage(
            aggregates,
            context.days,
            lambda item: self.policy.rank(item.best, priors),
        )
        reserve_deficit = len(meal_coverage.hard_missing_slots) + len(
            meal_coverage.reserve_missing_slots
        )
        diversity_deficit = coverage_shortfall(style_coverage)
        if reserve_deficit or diversity_deficit:
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
                        max(3, ceil(max(reserve_deficit, diversity_deficit) * 1.3)),
                    ),
                    excluded_restaurant_ids=excluded_ids,
                    required_meals=missing_meals(meal_coverage),
                )
            except Exception:
                general = []
            for candidate in self._deduplicate(general, context):
                reason = self.policy.ineligible_reason(candidate, context)
                if reason is not None:
                    rejected[reason] += 1
                else:
                    eligible.append(candidate)
            priors = self.policy.priors(eligible)
            diverse, style_coverage = select_style_item_candidates(
                eligible,
                context.days,
                priors,
                self.policy.rank,
                active_style_ids=active_style_ids,
            )
            preferred = {item.restaurant_id: item for item in diverse}
            aggregates = aggregate_restaurants(
                eligible,
                priors,
                self.policy.rank,
                preferred_by_restaurant=preferred,
            )
            meal_coverage = build_food_meal_coverage(
                aggregates,
                context.days,
                lambda item: self.policy.rank(item.best, priors),
            )

        selected_pool = select_food_pool(
            aggregates,
            context.days,
            priors,
            self.policy.rank,
            required_ids=(
                matched_restaurant_ids(meal_coverage)
                | {item.restaurant_id for item in diverse}
            ),
        )
        anchor_names = {anchor.place_id: anchor.name for anchor in anchors}
        selections = [
            self._to_selection(
                item,
                anchor_names,
                priors,
                diversity_restaurant_ids={item.restaurant_id for item in diverse},
            )
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
            *(
                [
                    "Food style diversity còn thiếu: "
                    + ", ".join(
                        f"{item.style_name}={item.selected_restaurants}/"
                        f"{item.target_items}"
                        for item in style_coverage
                        if not item.complete
                    )
                    + "."
                ]
                if any(not item.complete for item in style_coverage)
                else []
            ),
        ]
        return FoodSelectionBatch(
            selections=selections,
            unmatched_anchor_place_ids=unmatched,
            warnings=warnings,
            meal_coverage=meal_coverage,
            style_coverage=style_coverage,
        )

    def _to_selection(
        self,
        aggregate: RestaurantAggregate,
        anchor_names: dict[str, str],
        priors: dict[str, BayesianRatingPrior],
        *,
        diversity_restaurant_ids: set[str],
    ) -> SelectedFoodRestaurant:
        selected = aggregate.best
        bayesian = self.policy.bayesian(selected, priors)
        reason = (
            "style_item_diversity"
            if selected.restaurant_id in diversity_restaurant_ids
            else "sole_candidate_for_food"
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
            style_id=selected.style_id,
            style_name=selected.style_name,
            food_match_type=selected.food_match_type,
            food_match_confidence=selected.food_match_confidence,
            restaurant_id=selected.restaurant_id,
            restaurant_name=selected.restaurant_name,
            distance_km=selected.distance_km,
            rating=selected.metadata.rating,
            review_count=selected.metadata.review_count,
            bayesian_rating=bayesian,
            pair_score=self.policy.pair_score(selected, priors),
            selection_reason=reason,
            proximity_source=selected.proximity_source,
            evidence_types=list(aggregate.evidence_types),
            metadata=selected.metadata,
        )

    @classmethod
    def _deduplicate(
        cls,
        candidates: list[FoodRestaurantCandidate],
        context: TripEvaluationContext,
    ) -> list[FoodRestaurantCandidate]:
        """Keep one restaurant option per anchor without losing anchor coverage."""
        selected: dict[tuple[str, str, str, str], FoodRestaurantCandidate] = {}
        for candidate in candidates:
            key = (
                candidate.anchor_place_id,
                candidate.restaurant_id,
                candidate.food_item_id,
                candidate.style_id or "",
            )
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
            int(FoodCandidatePolicy.ineligible_reason(candidate, context) is None),
            int(candidate.food_match_type == "direct_id"),
            candidate.food_priority,
            candidate.food_confidence,
            candidate.offer_confidence,
            candidate.metadata.review_count or 0,
            candidate.food_item_id,
        )
