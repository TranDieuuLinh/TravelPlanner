"""Select one discovery query for each canonical pool that is still short."""

from __future__ import annotations

from app.modules.place_checker.analysis.contract import CoverageAnalysis
from app.modules.place_checker.selection.pool_policy import (
    ACCOMMODATION_POOL_TARGET,
    activity_pool_target_for_days,
    drink_dessert_pool_target_for_days,
    entertainment_pool_target_for_days,
    food_pool_target_for_days,
)


_CATEGORY_ALIASES = {
    "travel_place": {"travel place", "travel_place", "landmark", "garden"},
    "restaurant": {"food", "food venue", "restaurant"},
    "drink_dessert": {"cafe", "drink dessert", "drink_dessert"},
    "entertainment": {"entertainment"},
    "accommodation": {"accommodation", "hotel", "hostel"},
}

_QUERY_BY_POOL = {
    "travel_place": "pool:travel_place_candidates",
    "restaurant": "pool:restaurant_candidates",
    "drink_dessert": "pool:drink_dessert_candidates",
    "entertainment": "pool:entertainment_candidates",
    "accommodation": "pool:accommodation_candidates",
}


def select_adaptive_pool_specs(
    all_specs,
    gaps,
    coverage: CoverageAnalysis | None,
    *,
    days: int,
    excluded_gap_types,
):
    """Return at most one query per pool; gap fan-out no longer drives search."""
    del gaps
    if coverage is None:
        return {
            query_id: all_specs[query_id]
            for query_id in _QUERY_BY_POOL.values()
            if query_id in all_specs
            and all_specs[query_id][0] not in excluded_gap_types
        }

    counts = {
        pool: sum(coverage.category_distribution.get(alias, 0) for alias in aliases)
        for pool, aliases in _CATEGORY_ALIASES.items()
    }
    targets = {
        "travel_place": activity_pool_target_for_days(days),
        "restaurant": food_pool_target_for_days(days),
        "drink_dessert": drink_dessert_pool_target_for_days(days),
        "entertainment": entertainment_pool_target_for_days(days),
        "accommodation": ACCOMMODATION_POOL_TARGET,
    }
    selected = {}
    for pool, query_id in _QUERY_BY_POOL.items():
        gap_type = all_specs[query_id][0] if query_id in all_specs else None
        if (
            counts[pool] < targets[pool]
            and query_id in all_specs
            and gap_type not in excluded_gap_types
        ):
            selected[query_id] = all_specs[query_id]
    return selected
