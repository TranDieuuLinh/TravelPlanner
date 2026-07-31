"""
Tool 1: Region Overview - Overview statistics for a known region.

Provides category-level statistics, price distribution, and ratings
for a specific region (e.g., vn,vung-tau).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING

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
    """Extract price tier from place metadata."""
    prices = metadata.get("prices", [])
    if not prices:
        return None
    # Find first non-mock price
    for price in prices:
        if not price.get("isMock", False):
            return price.get("tier", price.get("priceRange"))
    return None


def _estimate_daily_cost(metadata: dict) -> int | None:
    """Estimate daily cost from place metadata prices."""
    prices = metadata.get("prices", [])
    if not prices:
        return None
    # Sum up cost estimates for a day
    total = 0
    count = 0
    for price in prices:
        if not price.get("isMock", False):
            amount = price.get("amount") or price.get("estimatedCost") or price.get("minCost")
            if amount:
                total += float(amount)
                count += 1
    return int(total / count) if count > 0 else None


def _normalize_category(place_type: str, tags: list[str]) -> str:
    """Normalize place type and tags to a canonical category."""
    place_type_lower = place_type.lower()
    tags_lower = {t.lower() for t in tags}

    # Direct mappings
    if place_type_lower in ("restaurant", "food", "fast_food", "food_court", "local_food"):
        return "food"
    if place_type_lower in ("cafe", "coffee_shop", "coffee"):
        return "cafe"
    if place_type_lower in ("beach", "seaside", "coast"):
        return "beach"
    if place_type_lower in ("park", "nature", "mountain", "waterfall", "garden", "forest"):
        return "nature"
    if place_type_lower in ("museum", "heritage", "historic", "temple", "pagoda", "church"):
        return "culture"
    if place_type_lower in ("market", "mall", "shopping_mall", "marketplace"):
        return "shopping"
    if place_type_lower in ("bar", "pub", "nightclub", "club"):
        return "nightlife"
    if place_type_lower in ("hotel", "hostel", "motel", "resort", "homestay"):
        return "accommodation"
    if place_type_lower in ("bus_station", "train_station", "airport", "port", "transport"):
        return "transport"
    if place_type_lower in ("attraction", "amusement", "viewpoint", "tourist_spot"):
        return "sightseeing"

    # Tag-based fallback
    if "food" in tags_lower or "restaurant" in tags_lower or "ăn uống" in tags_lower:
        return "food"
    if "cafe" in tags_lower or "cà phê" in tags_lower:
        return "cafe"
    if "beach" in tags_lower or "biển" in tags_lower:
        return "beach"
    if "nature" in tags_lower or "nature" in tags_lower or "thiên nhiên" in tags_lower:
        return "nature"
    if "culture" in tags_lower or "văn hóa" in tags_lower or "di sản" in tags_lower:
        return "culture"
    if "shopping" in tags_lower or "mua sắm" in tags_lower:
        return "shopping"
    if "nightlife" in tags_lower or "bar" in tags_lower:
        return "nightlife"

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

        metadata = place.metadata_json or {}
        tags = metadata.get("tags", [])

        # Get rating and review count
        rating = None
        if place.data_confidence in ("high", "medium"):
            # Try to get from metadata first
            rating = metadata.get("rating") or metadata.get("avgRating")
            if rating:
                rating = float(rating)
        if rating is None and place.status == "active":
            # Fallback: estimate from review count
            review_count = metadata.get("reviewCount") or metadata.get("review_count") or metadata.get("reviewcount", 0)
            if isinstance(review_count, (int, float)) and review_count > 0:
                rating = min(5.0, 3.5 + (float(review_count) / 100))

        review_count = metadata.get("reviewCount") or metadata.get("review_count") or metadata.get("reviewcount")
        if review_count and not isinstance(review_count, int):
            try:
                review_count = int(review_count)
            except (ValueError, TypeError):
                review_count = None

        price_tier = _extract_price_tier(metadata)
        daily_cost = _estimate_daily_cost(metadata)

        # Determine category
        category = _normalize_category(place.place_type, tags)

        self.categories[category].add(rating, review_count, price_tier, daily_cost)
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
