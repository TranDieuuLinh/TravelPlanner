"""Select only the reserve-pool searches needed by current coverage."""

from __future__ import annotations

from math import ceil

from app.modules.place_checker.analysis_contract import CoverageAnalysis
from app.modules.place_checker.enums import GapStatus, GapType
from app.modules.place_checker.pool_policy import (
    activity_pool_target_for_days,
    entertainment_pool_target_for_days,
)


_FOOD_CATEGORIES = {"food", "food venue", "restaurant"}
_ENTERTAINMENT_CATEGORIES = {
    "cafe",
    "drink dessert",
    "drink_dessert",
    "entertainment",
}
_ACCOMMODATION_CATEGORIES = {"hotel", "accommodation", "hostel"}
_TRAVEL_DISCOVERY_GAPS = {
    GapType.trip_capacity,
    GapType.experience_coverage,
    GapType.time_of_day,
    GapType.budget,
    GapType.diversity,
    GapType.geographic_balance,
    GapType.people_accessibility,
}
_TRAVEL_POOL_ORDER = (
    "pool:travel_place_candidates",
    "pool:popular_landmark_candidates",
    "pool:heritage_landmark_candidates",
    "pool:special_experience_candidates",
    "pool:culture_alternatives",
    "pool:nature_alternatives",
    "pool:shopping_alternatives",
    "pool:nightlife_alternatives",
    "pool:workshop_alternatives",
    "pool:performance_alternatives",
    "pool:outdoor_alternatives",
    "pool:family_alternatives",
    "pool:special_experience_alternatives",
    "pool:local_activity_alternatives",
    "pool:travel_place_reserve",
)


def select_adaptive_pool_specs(
    all_specs,
    gaps,
    coverage: CoverageAnalysis | None,
    *,
    days: int,
    excluded_gap_types: set[GapType],
):
    if coverage is None:
        return all_specs
    categories = coverage.category_distribution
    food_count = sum(categories.get(category, 0) for category in _FOOD_CATEGORIES)
    entertainment_count = sum(
        categories.get(category, 0) for category in _ENTERTAINMENT_CATEGORIES
    )
    accommodation_count = sum(
        categories.get(category, 0) for category in _ACCOMMODATION_CATEGORIES
    )
    travel_count = max(
        0,
        coverage.planner_eligible_place_count
        - food_count
        - entertainment_count
        - accommodation_count,
    )
    shortfall = max(0, activity_pool_target_for_days(days) - travel_count)
    existing_queries = sum(
        gap.status == GapStatus.open
        and gap.gap_type in _TRAVEL_DISCOVERY_GAPS
        and gap.gap_type not in excluded_gap_types
        for gap in gaps
    )
    # A filtered theme query commonly contributes fewer than its SQL top-K.
    # Budget around six usable candidates per query to avoid under-fetching.
    travel_query_count = max(0, ceil(shortfall / 6) - existing_queries)
    selected = {}
    for key in _TRAVEL_POOL_ORDER[:travel_query_count]:
        if key in all_specs:
            selected[key] = all_specs[key]
    if accommodation_count == 0 and "pool:accommodation_candidates" in all_specs:
        selected["pool:accommodation_candidates"] = all_specs[
            "pool:accommodation_candidates"
        ]
    if GapType.food_coverage not in excluded_gap_types and food_count < days * 3:
        if "pool:food_alternatives" in all_specs:
            selected["pool:food_alternatives"] = all_specs["pool:food_alternatives"]
    if entertainment_count < entertainment_pool_target_for_days(days):
        for key in ("pool:drink_alternatives", "pool:entertainment_alternatives"):
            if key in all_specs:
                selected[key] = all_specs[key]
    return selected
