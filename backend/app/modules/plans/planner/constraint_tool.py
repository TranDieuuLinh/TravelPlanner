"""
Tool 2: Constraint Research - Spatial + Category stats with constraints.

Provides statistics about places within a geographic radius, with filtering
by budget, duration, and interests/categories.

Supports two modes:
- coordinates: Direct lat/lng + radius search
- text: Text query that gets converted to coordinates (semantic search)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING, Protocol

from app.modules.plans.planner.place_metadata import (
    read_daily_cost,
    read_price_level,
    read_rating,
    read_tags,
)
from app.modules.plans.planner.research_tools_schema import (
    BudgetCompatibility,
    CategoryBudgetStat,
    CategoryStatsOutput,
    ConstraintResearchInput,
    ConstraintResearchOutput,
    SpatialStats,
    ZoneStat,
)

if TYPE_CHECKING:
    from app.modules.places.model import Place


# ============================================================================
# Constants
# ============================================================================

EARTH_RADIUS_KM = 6371.0
GRID_CELL_SIZE_KM = 10.0  # Grid cell size for zone clustering


# ============================================================================
# Price Tier Normalization
# ============================================================================

def _normalize_price_tier(raw_tier: str | None) -> str | None:
    """Normalize price tier to standard format."""
    if raw_tier is None:
        return None
    tier = raw_tier.lower().strip()
    if tier in ("$", "low", "budget", "bình dân", "rẻ"):
        return "$"
    if tier in ("$$", "medium", "trung bình", "tb"):
        return "$$"
    if tier in ("$$$", "high", "cao cấp"):
        return "$$$"
    if tier in ("$$$$", "luxury", "sang trọng"):
        return "$$$$"
    return "$$"  # Default to medium


def _estimate_daily_cost(metadata: dict) -> int | None:
    """Estimate daily cost from place metadata prices (legacy or new schema)."""

    legacy_prices = metadata.get("prices", [])
    if isinstance(legacy_prices, list) and legacy_prices:
        total = 0.0
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

    tier = _normalize_price_tier(_read_price_tier(metadata))
    if tier:
        from app.modules.plans.planner.place_metadata import _price_level_to_cost

        cost = _price_level_to_cost(tier)
        if cost is not None:
            return cost

    return None


def _read_price_tier(metadata: dict) -> str | None:
    """Read a price tier string out of either schema's metadata shape."""

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


# ============================================================================
# Category Normalization
# ============================================================================

CANONICAL_CATEGORIES = {
    "food", "cafe", "beach", "nature", "culture", "shopping",
    "nightlife", "accommodation", "transport", "sightseeing",
    "entertainment", "attraction", "wellness", "other",
}


from app.modules.plans.planner.region_overview_tool import (  # noqa: E402
    TAG_CATEGORY_HINTS as _TAG_CATEGORY_HINTS,
)


def _normalize_category(place_type: str, tags: list[str]) -> str:
    """Normalize place type and tags to a canonical category.

    Mirrors the behaviour of :func:`region_overview_tool._normalize_category`
    but is duplicated here to keep the two tools self-contained.
    """

    from app.modules.plans.planner.region_overview_tool import (
        GOOGLE_PLACE_TYPE_CATEGORY,
        LEGACY_PLACE_TYPE_CATEGORY,
    )

    place_type_lower = (place_type or "").lower()
    if place_type_lower in GOOGLE_PLACE_TYPE_CATEGORY:
        return GOOGLE_PLACE_TYPE_CATEGORY[place_type_lower]
    if place_type_lower in LEGACY_PLACE_TYPE_CATEGORY:
        return LEGACY_PLACE_TYPE_CATEGORY[place_type_lower]

    tags_lower = {(t or "").lower() for t in tags}
    for hint, category in _TAG_CATEGORY_HINTS.items():
        if hint in tags_lower:
            return category

    return "other"


# ============================================================================
# Haversine Distance
# ============================================================================

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def is_within_radius(center_lat: float, center_lng: float, point_lat: float, point_lng: float, radius_km: float) -> bool:
    """Check if a point is within a given radius from center."""
    return haversine_km(center_lat, center_lng, point_lat, point_lng) <= radius_km


# ============================================================================
# Grid-based Zone Clustering
# ============================================================================

@dataclass
class _ZoneAccumulator:
    """Accumulates statistics for a grid zone."""
    zone_id: str
    center_lat: float = 0.0
    center_lng: float = 0.0
    place_count: int = 0
    ratings: list[float] = field(default_factory=list)
    daily_costs: list[int] = field(default_factory=list)
    categories: set[str] = field(default_factory=set)
    category_stats: dict[str, dict] = field(default_factory=lambda: defaultdict(lambda: {
        "count": 0, "ratings": [], "daily_costs": [], "price_tiers": defaultdict(int)
    }))

    def add_place(self, place: Place) -> None:
        self.place_count += 1
        self.center_lat += float(place.latitude)
        self.center_lng += float(place.longitude)

        tags = read_tags(place)
        metadata = place.metadata_json or {}

        rating = read_rating(place)
        cost = _estimate_daily_cost(metadata)
        if cost is None:
            cost = read_daily_cost(place)

        category = _normalize_category(place.place_type, tags)
        self.categories.add(category)

        cat_stats = self.category_stats[category]
        cat_stats["count"] += 1
        if rating is not None:
            cat_stats["ratings"].append(rating)
        if cost:
            cat_stats["daily_costs"].append(cost)
        price_tier = _normalize_price_tier(_read_price_tier(metadata) or read_price_level(place))
        if price_tier:
            cat_stats["price_tiers"][price_tier] += 1

    def finalize(self) -> ZoneStat:
        """Finalize zone statistics."""
        if self.place_count > 0:
            avg_lat = self.center_lat / self.place_count
            avg_lng = self.center_lng / self.place_count
        else:
            avg_lat = 0.0
            avg_lng = 0.0

        avg_rating = round(mean(self.ratings), 1) if self.ratings else None
        avg_daily = int(mean(self.daily_costs)) if self.daily_costs else None

        # Top categories by count
        top_cats = sorted(
            self.categories,
            key=lambda c: -self.category_stats[c]["count"]
        )[:5]

        return ZoneStat(
            zone_id=self.zone_id,
            center_lat=round(avg_lat, 7),
            center_lng=round(avg_lng, 7),
            place_count=self.place_count,
            avg_rating=avg_rating,
            avg_daily_cost=avg_daily,
            top_categories=top_cats,
        )


def _get_grid_zone_id(lat: float, lng: float) -> tuple[int, int]:
    """Get grid cell coordinates for a lat/lng point."""
    # Approximate degrees per km at equator
    lat_deg_per_km = 1.0 / 111.0
    lng_deg_per_km = 1.0 / (111.0 * math.cos(math.radians(lat)))

    cell_lat = int(lat / (GRID_CELL_SIZE_KM * lat_deg_per_km))
    cell_lng = int(lng / (GRID_CELL_SIZE_KM * lng_deg_per_km))

    return (cell_lat, cell_lng)


# ============================================================================
# Main Calculation Logic
# ============================================================================

def calculate_constraint_research(
    places: list[Place],
    input_data: ConstraintResearchInput,
) -> ConstraintResearchOutput:
    """
    Calculate constraint research statistics from a list of places.

    Args:
        places: List of Place objects to analyze
        input_data: Constraint research input with coordinates/budget/interests

    Returns:
        ConstraintResearchOutput with spatial, category, and budget statistics
    """
    # Filter places within radius
    if input_data.mode == "coordinates":
        filtered_places = [
            p for p in places
            if p.latitude is not None and p.longitude is not None
            and is_within_radius(
                input_data.center_lat,
                input_data.center_lng,
                float(p.latitude),
                float(p.longitude),
                input_data.radius_km,
            )
        ]
    else:
        # For text mode, we would need embedding search
        # For now, use all places (would be replaced by actual semantic search)
        filtered_places = places

    # Interest filtering
    if input_data.interests:
        interest_set = {i.lower() for i in input_data.interests}
        filtered_places = [
            p for p in filtered_places
            if _place_matches_interests(p, interest_set)
        ]

    # Grid-based zone clustering
    zones: dict[tuple[int, int], _ZoneAccumulator] = defaultdict(
        lambda: _ZoneAccumulator(zone_id="")
    )

    for place in filtered_places:
        if place.latitude is None or place.longitude is None:
            continue
        cell = _get_grid_zone_id(float(place.latitude), float(place.longitude))
        if zones[cell].zone_id == "":
            zones[cell].zone_id = f"zone_{cell[0]}_{cell[1]}"
        zones[cell].add_place(place)

    # Build spatial stats
    zone_stats = [zone.finalize() for zone in zones.values() if zone.place_count > 0]
    zone_stats.sort(key=lambda z: -z.place_count)  # Sort by place count desc

    total_zones = len(zone_stats)
    total_places = sum(z.place_count for z in zone_stats)

    spatial_stats = SpatialStats(
        zones=zone_stats,
        total_zones_in_radius=total_zones,
        total_places_in_radius=total_places,
    )

    # Build category stats
    category_stats = _build_category_stats(filtered_places, input_data.interests)

    # Build budget compatibility
    budget_compat = _build_budget_compatibility(
        filtered_places,
        input_data.budget,
        input_data.duration,
    )

    return ConstraintResearchOutput(
        spatial_stats=spatial_stats,
        category_stats=category_stats,
        budget_compatibility=budget_compat,
    )


def _place_matches_interests(place: Place, interests: set[str]) -> bool:
    """Check if a place matches any of the given interests."""

    tags = {t.lower() for t in read_tags(place)}
    metadata = place.metadata_json or {}
    google_payload = metadata.get("google") if isinstance(metadata, dict) else None
    google_category = (
        google_payload.get("category").lower()
        if isinstance(google_payload, dict) and isinstance(google_payload.get("category"), str)
        else ""
    )

    place_type_lower = (place.place_type or "").lower()

    for interest in interests:
        interest_lower = interest.lower()
        if (
            interest_lower in place_type_lower
            or interest_lower in google_category
            or interest_lower in tags
            or interest_lower in place.name.lower()
        ):
            return True
    return False


def _build_category_stats(places: list[Place], interests: list[str]) -> CategoryStatsOutput:
    """Build category statistics from places."""
    category_accumulators: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "count_with_price": 0, "ratings": [], "daily_costs": [], "price_tiers": defaultdict(int)}
    )

    for place in places:
        tags = read_tags(place)
        category = _normalize_category(place.place_type, tags)

        acc = category_accumulators[category]
        acc["count"] += 1

        rating = read_rating(place)
        if rating is not None:
            acc["ratings"].append(rating)

        cost = _estimate_daily_cost(place.metadata_json or {})
        if cost is None:
            cost = read_daily_cost(place)
        if cost:
            acc["count_with_price"] += 1
            acc["daily_costs"].append(cost)

        price_tier = _normalize_price_tier(
            _read_price_tier(place.metadata_json or {}) or read_price_level(place)
        )
        if price_tier:
            acc["price_tiers"][price_tier] += 1

    # Build output
    result = CategoryStatsOutput()
    for cat_name in CANONICAL_CATEGORIES:
        acc = category_accumulators.get(cat_name) or {
            "count": 0,
            "count_with_price": 0,
            "ratings": [],
            "daily_costs": [],
            "price_tiers": defaultdict(int),
        }
        if acc["count"] > 0:
            stat = CategoryBudgetStat(
                count=acc["count"],
                count_with_price=acc["count_with_price"],
                avg_rating=round(mean(acc["ratings"]), 1) if acc["ratings"] else None,
                price_distribution=dict(acc["price_tiers"]),
                avg_daily_cost=int(mean(acc["daily_costs"])) if acc["daily_costs"] else None,
            )
            setattr(result, cat_name, stat)

    return result


def _build_budget_compatibility(
    places: list[Place],
    budget: int | None,
    duration: int | None,
) -> BudgetCompatibility | None:
    """Build budget compatibility analysis."""
    if budget is None:
        return None

    # Calculate average daily cost
    daily_costs = []
    for place in places:
        metadata = place.metadata_json or {}
        cost = _estimate_daily_cost(metadata)
        if cost is None:
            cost = read_daily_cost(place)
        if cost:
            daily_costs.append(cost)

    if not daily_costs:
        return BudgetCompatibility(
            within_budget=True,
            estimated_total_cost=None,
            left_over=budget,
            daily_budget=budget // duration if duration else None,
        )

    avg_daily = int(mean(daily_costs))
    num_days = duration or 3  # Default to 3 days if not specified

    estimated_total = avg_daily * num_days
    within = estimated_total <= budget
    leftover = budget - estimated_total if within else None

    return BudgetCompatibility(
        within_budget=within,
        estimated_total_cost=estimated_total,
        left_over=leftover,
        daily_budget=budget // num_days if num_days > 0 else None,
    )


# ============================================================================
# Repository Interface for Dependency Injection
# ============================================================================

class PlaceRepositoryForConstraint(Protocol):
    """Protocol for place repository supporting constraint research."""
    def list_within_radius(
        self,
        center_lat: float,
        center_lng: float,
        radius_km: float,
    ) -> list[Place]: ...

    def list_all_active(self) -> list[Place]: ...


class ConstraintResearchTool:
    """
    Tool implementation for constraint_research.
    Accepts a repository for dependency injection.
    """

    def __init__(self, repository: PlaceRepositoryForConstraint) -> None:
        self._repository = repository

    def execute(self, input_data: ConstraintResearchInput) -> ConstraintResearchOutput:
        """Execute the constraint research tool."""
        if input_data.mode == "coordinates":
            places = self._repository.list_within_radius(
                input_data.center_lat,
                input_data.center_lng,
                input_data.radius_km,
            )
        else:
            # Text mode: would need semantic search implementation
            # For now, fetch all and let the function filter
            places = self._repository.list_all_active()

        return calculate_constraint_research(places, input_data)
