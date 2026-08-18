from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from app.modules.place_checker.food_selection_contract import (
    FoodRestaurantCandidate,
    FoodStyleCoverage,
)
from app.shared.tools.bayesian_rating import BayesianRatingPrior


ITEMS_PER_STYLE_PER_DAY = 2
FOOD_DRINK_STYLES = {
    "style_breakfast": "Ăn sáng",
    "style_lunch": "Ăn trưa",
    "style_dinner": "Ăn tối",
    "style_drinking": "Ăn nhậu",
    "style_food_relaxation": "Ẩm thực & Thư giãn",
    "style_nightlife": "Cuộc sống về đêm",
}
DEFAULT_MEAL_STYLE_IDS = frozenset(
    {"style_breakfast", "style_lunch", "style_dinner"}
)
CandidateRank = Callable[
    [FoodRestaurantCandidate, dict[str, BayesianRatingPrior]], tuple
]


def select_style_item_candidates(
    candidates: list[FoodRestaurantCandidate],
    days: int,
    priors: dict[str, BayesianRatingPrior],
    rank: CandidateRank,
    *,
    active_style_ids: set[str] | None = None,
) -> tuple[list[FoodRestaurantCandidate], list[FoodStyleCoverage]]:
    """Select unique venues while cycling items inside each anchor region."""
    styled = [item for item in candidates if item.style_id and item.style_name]
    if not styled:
        # Compatibility sources may not expose Style provenance yet. Keep the
        # existing meal-pool behavior instead of reporting six synthetic gaps.
        return [], []
    active = active_style_ids or set(DEFAULT_MEAL_STYLE_IDS)
    styles: dict[str, list[FoodRestaurantCandidate]] = {
        style_id: []
        for style_id in FOOD_DRINK_STYLES
        if style_id in active
    }
    for candidate in styled:
        if candidate.style_id in styles:
            styles[candidate.style_id].append(candidate)

    target = days * ITEMS_PER_STYLE_PER_DAY
    selected: list[FoodRestaurantCandidate] = []
    selected_restaurants: set[str] = set()
    global_item_counts: Counter[str] = Counter()
    region_style_counts: Counter[tuple[str, str]] = Counter()
    region_item_counts: Counter[tuple[str, str, str]] = Counter()
    selected_by_style: Counter[str] = Counter()
    selected_items_by_style: dict[str, set[str]] = {
        style_id: set() for style_id in styles
    }

    # Scarce styles choose first so broad breakfast/dinner pools cannot consume
    # the few nightlife or drinking venues that are available in a region.
    ordered_styles = sorted(
        styles,
        key=lambda style_id: (
            len({item.restaurant_id for item in styles[style_id]}),
            len({item.food_item_id for item in styles[style_id]}),
            style_id,
        ),
    )
    for style_id in ordered_styles:
        options = styles[style_id]
        while selected_by_style[style_id] < target:
            available = [
                item
                for item in options
                if item.restaurant_id not in selected_restaurants
            ]
            if not available:
                break
            chosen = min(
                available,
                key=lambda item: (
                    region_style_counts[(item.anchor_place_id, style_id)],
                    region_item_counts[
                        (item.anchor_place_id, style_id, item.food_item_id)
                    ],
                    global_item_counts[item.food_item_id],
                    tuple(
                        -value if isinstance(value, (int, float)) else value
                        for value in rank(item, priors)[:-1]
                    ),
                    item.restaurant_id,
                ),
            )
            selected.append(chosen)
            selected_restaurants.add(chosen.restaurant_id)
            selected_by_style[style_id] += 1
            selected_items_by_style[style_id].add(chosen.food_item_id)
            global_item_counts[chosen.food_item_id] += 1
            region_style_counts[(chosen.anchor_place_id, style_id)] += 1
            region_item_counts[
                (chosen.anchor_place_id, style_id, chosen.food_item_id)
            ] += 1

    coverage = [
        FoodStyleCoverage(
            style_id=style_id,
            style_name=(
                styles[style_id][0].style_name
                if styles[style_id]
                else FOOD_DRINK_STYLES[style_id]
            ),
            target_items=target,
            selected_restaurants=selected_by_style[style_id],
            distinct_items=len(selected_items_by_style[style_id]),
            complete=selected_by_style[style_id] >= target,
        )
        for style_id in sorted(styles)
    ]
    return selected, coverage


def coverage_shortfall(coverage: list[FoodStyleCoverage]) -> int:
    return sum(
        max(0, item.target_items - item.selected_restaurants) for item in coverage
    )
