"""
Tool 1: Region Overview - Overview statistics for a known region.

Provides category-level statistics, price distribution, and ratings
for a specific region (e.g., vn,vung-tau).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING, Protocol

from app.modules.plans.planner.place_metadata import (
    read_daily_cost,
    read_price_level,
    read_rating,
    read_review_count,
    read_tags,
)
from app.modules.plans.planner.research_tools_schema import (
    CategoryStat,
    RegionOverviewInput,
    RegionOverviewOutput,
)

if TYPE_CHECKING:
    from app.modules.places.model import Place


@dataclass
class _CategoryAccumulator:
    """Accumulates statistics for a single category."""
    place_ids: list[str] = field(default_factory=list)
    ratings: list[float] = field(default_factory=list)
    review_counts: list[int] = field(default_factory=list)
    prices: list[int] = field(default_factory=list)  # daily cost estimates
    price_tiers: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, rating: float | None, review_count: int | None, price_tier: str | None, daily_cost: int | None) -> None:
        self.place_ids.append("")
        if rating is not None:
            self.ratings.append(rating)
        if review_count is not None:
            self.review_counts.append(review_count)
        if price_tier is not None:
            self.price_tiers[price_tier] += 1
        if daily_cost is not None:
            self.prices.append(daily_cost)


def _extract_price_tier(metadata: dict) -> str | None:
    """Extract price tier from place metadata (legacy or new schema)."""

    legacy_prices = metadata.get("prices", [])
    if isinstance(legacy_prices, list) and legacy_prices:
        for price in legacy_prices:
            if not isinstance(price, dict):
                continue
            if price.get("isMock"):
                continue
            tier = price.get("tier") or price.get("priceRange")
            if isinstance(tier, str) and tier.strip():
                return tier.strip()
        return None

    for key in ("priceLevel", "price_level", "priceRange", "price_range"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            tier = value.get("tier") or value.get("label")
            if isinstance(tier, str) and tier.strip():
                return tier.strip()

    google_payload = metadata.get("google") if isinstance(metadata, dict) else None
    if isinstance(google_payload, dict):
        for key in ("priceLevel", "price_level"):
            value = google_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _estimate_daily_cost(metadata: dict) -> int | None:
    """Estimate daily cost from place metadata prices (legacy or new schema)."""

    legacy_prices = metadata.get("prices", [])
    if isinstance(legacy_prices, list) and legacy_prices:
        total = 0
        count = 0
        for price in legacy_prices:
            if not isinstance(price, dict) or price.get("isMock"):
                continue
            amount = price.get("amount") or price.get("estimatedCost") or price.get("minCost")
            if amount:
                total += float(amount)
                count += 1
        if count > 0:
            return int(total / count)

    finance = metadata.get("finance") if isinstance(metadata, dict) else None
    if isinstance(finance, dict):
        raw = finance.get("dailyBudget") or finance.get("estimatedCost")
        if raw is not None:
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                pass

    tier = _extract_price_tier(metadata)
    if tier:
        from app.modules.plans.planner.place_metadata import _price_level_to_cost

        cost = _price_level_to_cost(tier)
        if cost is not None:
            return cost

    return None


GOOGLE_PLACE_TYPE_CATEGORY: dict[str, str] = {
    "accounting": "shopping",
    "airport": "transport",
    "amusement_park": "entertainment",
    "aquarium": "attraction",
    "art_gallery": "culture",
    "atm": "shopping",
    "bakery": "food",
    "bank": "shopping",
    "bar": "nightlife",
    "beauty_salon": "shopping",
    "bicycle_store": "shopping",
    "book_store": "shopping",
    "bowling_alley": "entertainment",
    "bus_station": "transport",
    "cafe": "cafe",
    "campground": "nature",
    "car_dealer": "shopping",
    "car_rental": "transport",
    "car_repair": "shopping",
    "car_wash": "shopping",
    "casino": "entertainment",
    "cemetery": "culture",
    "church": "culture",
    "city_hall": "culture",
    "clothing_store": "shopping",
    "convenience_store": "shopping",
    "courthouse": "culture",
    "dentist": "shopping",
    "department_store": "shopping",
    "doctor": "shopping",
    "drugstore": "shopping",
    "electrician": "shopping",
    "electronics_store": "shopping",
    "embassy": "culture",
    "fire_station": "transport",
    "florist": "shopping",
    "funeral_home": "shopping",
    "furniture_store": "shopping",
    "gas_station": "transport",
    "gym": "entertainment",
    "hair_care": "shopping",
    "hardware_store": "shopping",
    "hindu_temple": "culture",
    "home_goods_store": "shopping",
    "hospital": "shopping",
    "insurance_agency": "shopping",
    "jewelry_store": "shopping",
    "laundry": "shopping",
    "lawyer": "shopping",
    "library": "culture",
    "light_rail_station": "transport",
    "liquor_store": "shopping",
    "local_government_office": "culture",
    "locksmith": "shopping",
    "lodging": "accommodation",
    "meal_delivery": "food",
    "meal_takeaway": "food",
    "mosque": "culture",
    "movie_rental": "entertainment",
    "movie_theater": "entertainment",
    "moving_company": "transport",
    "museum": "culture",
    "natural_feature": "nature",
    "neighborhood": "other",
    "night_club": "nightlife",
    "park": "nature",
    "parking": "transport",
    "pet_store": "shopping",
    "pharmacy": "shopping",
    "physiotherapist": "shopping",
    "place_of_worship": "culture",
    "plumber": "shopping",
    "point_of_interest": "sightseeing",
    "police": "shopping",
    "post_office": "shopping",
    "real_estate_agency": "shopping",
    "restaurant": "food",
    "roofing_contractor": "shopping",
    "rv_park": "accommodation",
    "school": "culture",
    "spa": "wellness",
    "stadium": "entertainment",
    "storage": "shopping",
    "store": "shopping",
    "subway_station": "transport",
    "supermarket": "shopping",
    "synagogue": "culture",
    "taxi_stand": "transport",
    "tourist_attraction": "sightseeing",
    "train_station": "transport",
    "travel_agency": "shopping",
    "university": "culture",
    "veterinary_care": "shopping",
    "zoo": "attraction",
}


LEGACY_PLACE_TYPE_CATEGORY: dict[str, str] = {
    "restaurant": "food",
    "food": "food",
    "fast_food": "food",
    "food_court": "food",
    "local_food": "food",
    "do_an": "food",
    "an_uong": "food",
    "cafe": "cafe",
    "coffee_shop": "cafe",
    "coffee": "cafe",
    "ca_phe": "cafe",
    "beach": "beach",
    "seaside": "beach",
    "coast": "beach",
    "bien": "beach",
    "park": "nature",
    "nature": "nature",
    "mountain": "nature",
    "waterfall": "nature",
    "garden": "nature",
    "forest": "nature",
    "nui": "nature",
    "thien_nhien": "nature",
    "museum": "culture",
    "heritage": "culture",
    "historic": "culture",
    "temple": "culture",
    "pagoda": "culture",
    "church": "culture",
    "van_hoa": "culture",
    "di_san": "culture",
    "market": "shopping",
    "mall": "shopping",
    "shopping_mall": "shopping",
    "marketplace": "shopping",
    "mua_sam": "shopping",
    "bar": "nightlife",
    "pub": "nightlife",
    "nightclub": "nightlife",
    "club": "nightlife",
    "bar_club": "nightlife",
    "hotel": "accommodation",
    "hostel": "accommodation",
    "motel": "accommodation",
    "resort": "accommodation",
    "homestay": "accommodation",
    "noi_that": "accommodation",
    "bus_station": "transport",
    "train_station": "transport",
    "airport": "transport",
    "port": "transport",
    "transport": "transport",
    "ga": "transport",
    "attraction": "sightseeing",
    "amusement": "sightseeing",
    "viewpoint": "sightseeing",
    "tourist_spot": "sightseeing",
    "dia_diem": "sightseeing",
}


TAG_CATEGORY_HINTS: dict[str, str] = {
    "food": "food",
    "restaurant": "food",
    "an_uong": "food",
    "cafe": "cafe",
    "ca_phe": "cafe",
    "beach": "beach",
    "bien": "beach",
    "nature": "nature",
    "thien_nhien": "nature",
    "culture": "culture",
    "van_hoa": "culture",
    "di_san": "culture",
    "shopping": "shopping",
    "mua_sam": "shopping",
    "nightlife": "nightlife",
    "attraction": "sightseeing",
    "dia_diem": "sightseeing",
}


def _normalize_category(place_type: str, tags: list[str]) -> str:
    """Normalize place type and tags to a canonical category."""

    place_type_lower = (place_type or "").lower()
    if place_type_lower in GOOGLE_PLACE_TYPE_CATEGORY:
        return GOOGLE_PLACE_TYPE_CATEGORY[place_type_lower]
    if place_type_lower in LEGACY_PLACE_TYPE_CATEGORY:
        return LEGACY_PLACE_TYPE_CATEGORY[place_type_lower]

    tags_lower = {(t or "").lower() for t in tags}
    for hint, category in TAG_CATEGORY_HINTS.items():
        if hint in tags_lower:
            return category

    return "other"


@dataclass
class _RegionAccumulator:
    """Accumulates all statistics for a region."""
    categories: dict[str, _CategoryAccumulator] = field(default_factory=lambda: defaultdict(_CategoryAccumulator))
    total_places: int = 0
    active_places: int = 0
    all_ratings: list[float] = field(default_factory=list)

    def add_place(self, place: Place) -> None:
        self.total_places += 1
        if place.status == "active":
            self.active_places += 1

        tags = read_tags(place)
        metadata = place.metadata_json or {}

        rating = read_rating(place) if place.data_confidence in ("high", "medium") else None
        if rating is None and place.status == "active":
            review_count = read_review_count(place)
            if review_count > 0:
                rating = min(5.0, 3.5 + (review_count / 100))

        review_count_value = read_review_count(place) or None

        price_tier = _extract_price_tier(metadata) or read_price_level(place)
        daily_cost = _estimate_daily_cost(metadata)
        if daily_cost is None:
            daily_cost = read_daily_cost(place)

        category = _normalize_category(place.place_type, tags)

        self.categories[category].add(rating, review_count_value, price_tier, daily_cost)
        if rating is not None:
            self.all_ratings.append(rating)


def _build_category_stat(cat: str, acc: _CategoryAccumulator) -> CategoryStat:
    """Build CategoryStat from accumulator."""
    avg_rating = round(mean(acc.ratings), 1) if acc.ratings else None
    avg_review = round(mean(acc.review_counts)) if acc.review_counts else None
    avg_cost = int(mean(acc.prices)) if acc.prices else None

    return CategoryStat(
        count=len(acc.place_ids),
        count_with_price=len(acc.prices),
        avg_rating=avg_rating,
        avg_review_count=avg_review,
        price_distribution=dict(acc.price_tiers),
        avg_daily_cost=avg_cost,
    )


def calculate_region_overview(
    places: list[Place],
    input_data: RegionOverviewInput,
) -> RegionOverviewOutput:
    """
    Calculate region overview statistics from a list of places.

    Args:
        places: List of Place objects for the region
        input_data: Region overview input with region_key

    Returns:
        RegionOverviewOutput with category stats, price distribution, and ratings
    """
    accumulator = _RegionAccumulator()

    for place in places:
        # Filter by region_key prefix
        if place.region_key.startswith(f"{input_data.region_key},") or place.region_key == input_data.region_key:
            accumulator.add_place(place)

    category_stats = {
        cat: _build_category_stat(cat, acc)
        for cat, acc in sorted(accumulator.categories.items())
    }

    avg_overall = round(mean(accumulator.all_ratings), 1) if accumulator.all_ratings else None

    return RegionOverviewOutput(
        region_key=input_data.region_key,
        total_places=accumulator.total_places,
        active_places=accumulator.active_places,
        category_stats=category_stats,
        avg_overall_rating=avg_overall,
    )


# ============================================================================
# Repository Interface for Dependency Injection
# ============================================================================

from typing import Protocol


class PlaceRepositoryForOverview(Protocol):
    """Protocol for place repository supporting region overview."""
    def list_for_overview(self, region_key: str) -> list[Place]: ...


class RegionOverviewTool:
    """
    Tool implementation for region_overview.
    Accepts a repository for dependency injection.
    """

    def __init__(self, repository: PlaceRepositoryForOverview) -> None:
        self._repository = repository

    def execute(self, input_data: RegionOverviewInput) -> RegionOverviewOutput:
        """Execute the region overview tool."""
        places = self._repository.list_for_overview(input_data.region_key)
        return calculate_region_overview(places, input_data)
