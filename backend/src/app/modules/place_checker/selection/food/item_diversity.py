from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from app.modules.place_checker.selection.food.contract import FoodRestaurantCandidate
from app.shared.tools.bayesian_rating import BayesianRatingPrior


CandidateRank = Callable[
    [FoodRestaurantCandidate, dict[str, BayesianRatingPrior]], tuple
]


def select_food_item_candidates(
    candidates: list[FoodRestaurantCandidate],
    days: int,
    priors: dict[str, BayesianRatingPrior],
    rank: CandidateRank,
) -> list[FoodRestaurantCandidate]:
    """Select unique restaurants while spreading food items and real anchors."""
    target = min(len({item.restaurant_id for item in candidates}), max(6, days * 6))
    selected: list[FoodRestaurantCandidate] = []
    selected_restaurants: set[str] = set()
    item_counts: Counter[str] = Counter()
    anchor_counts: Counter[str] = Counter()

    while len(selected) < target:
        available = [
            item
            for item in candidates
            if item.restaurant_id not in selected_restaurants
        ]
        if not available:
            break
        chosen = max(
            available,
            key=lambda item: (
                item_counts[item.food_item_id] == 0,
                -anchor_counts[item.anchor_place_id],
                -item_counts[item.food_item_id],
                rank(item, priors),
            ),
        )
        selected.append(chosen)
        selected_restaurants.add(chosen.restaurant_id)
        item_counts[chosen.food_item_id] += 1
        anchor_counts[chosen.anchor_place_id] += 1
    return selected
