from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.place_checker.selection.food.contract import FoodRestaurantCandidate
from app.modules.place_checker.selection.pool_policy import food_pool_target_for_days
from app.modules.place_checker.planning.time_windows import meals_for_hours
from app.shared.tools.bayesian_rating import BayesianRatingPrior


MEALS = ("breakfast", "lunch", "dinner")
MAX_FOOD_POOL = 180
CandidateRank = Callable[
    [FoodRestaurantCandidate, dict[str, BayesianRatingPrior]], tuple
]


@dataclass(frozen=True)
class RestaurantAggregate:
    best: FoodRestaurantCandidate
    related_anchor_ids: tuple[str, ...]
    evidence_types: tuple[str, ...]
    food_peer_count: int


def aggregate_restaurants(
    candidates: list[FoodRestaurantCandidate],
    priors: dict[str, BayesianRatingPrior],
    rank: CandidateRank,
    *,
    preferred_by_restaurant: dict[str, FoodRestaurantCandidate] | None = None,
) -> list[RestaurantAggregate]:
    grouped: dict[str, list[FoodRestaurantCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.restaurant_id].append(candidate)
    food_peer_counts = {
        food_id: len(
            {item.restaurant_id for item in candidates if item.food_item_id == food_id}
        )
        for food_id in {item.food_item_id for item in candidates}
    }
    result = []
    preferred_by_restaurant = preferred_by_restaurant or {}
    for options in grouped.values():
        best = preferred_by_restaurant.get(options[0].restaurant_id) or max(
            options, key=lambda item: rank(item, priors)
        )
        related = tuple(
            dict.fromkeys(
                item.anchor_place_id
                for item in sorted(
                    options,
                    key=lambda item: item.distance_km or 999.0,
                )
                if item.proximity_source != "general_adm"
            )
        )
        evidence = tuple(
            dict.fromkeys(
                [
                    *(item.food_match_type for item in options),
                    *(
                        relation.relationship_type
                        for item in options
                        for relation in item.metadata.relationships
                    ),
                ]
            )
        )
        result.append(
            RestaurantAggregate(
                best,
                related,
                evidence,
                food_peer_counts[best.food_item_id],
            )
        )
    return result


def select_food_pool(
    candidates: list[RestaurantAggregate],
    days: int,
    priors: dict[str, BayesianRatingPrior],
    rank: CandidateRank,
    *,
    required_ids: set[str] | None = None,
) -> list[RestaurantAggregate]:
    hard_total = min(MAX_FOOD_POOL, days * len(MEALS))
    soft_total = min(MAX_FOOD_POOL, food_pool_target_for_days(days))
    selected: list[RestaurantAggregate] = []
    remaining = list(candidates)
    meal_counts = {meal: 0 for meal in MEALS}
    required_ids = required_ids or set()
    while remaining and len(selected) < soft_total:
        hard_incomplete = len(selected) < hard_total or any(
            meal_counts[meal] < days for meal in MEALS
        )
        desired = days if hard_incomplete else days * 2
        chosen = max(
            remaining,
            key=lambda item: (
                item.best.restaurant_id in required_ids,
                sum(
                    meal_counts[meal] < desired
                    for meal in meals_for_hours(item.best.metadata.opening_hours)
                ),
                rank(item.best, priors),
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)
        for meal in meals_for_hours(chosen.best.metadata.opening_hours):
            meal_counts[meal] += 1
        if len(selected) >= soft_total and all(
            meal_counts[meal] >= days * 2 for meal in MEALS
        ):
            break
    return selected
