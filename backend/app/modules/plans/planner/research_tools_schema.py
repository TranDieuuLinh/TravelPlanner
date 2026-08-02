"""
Schema definitions for Planner Research Tools.
These schemas define the input/output contracts for:
1. region_overview - overview statistics for a known region
2. constraint_research - spatial + category stats with constraints
3. festival_discovery - festival/holiday discovery
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


# ============================================================================
# Tool 1: Region Overview
# ============================================================================

class RegionOverviewInput(BaseModel):
    """Input for region_overview tool."""
    region_key: Annotated[str, Field(description="Region key, e.g. vn,vung-tau")]

    model_config = {"extra": "forbid"}


class CategoryStat(BaseModel):
    """Statistics for a single category."""
    count: int = Field(description="Total places in this category")
    count_with_price: Annotated[
        int,
        Field(alias="countWithPrice", description="Places that have price range data")
    ] = Field(default=0)
    avg_rating: Annotated[float | None, Field(alias="avgRating")] = Field(default=None)
    avg_review_count: Annotated[
        float | None,
        Field(alias="avgReviewCount", description="Average number of reviews")
    ] = Field(default=None)
    price_distribution: Annotated[
        dict[str, int],
        Field(alias="priceDistribution", description="Count by price tier: $, $$, $$$, $$$$")
    ] = Field(default_factory=dict)
    avg_daily_cost: Annotated[
        int | None,
        Field(alias="avgDailyCost", description="Estimated average daily cost in VND")
    ] = Field(default=None)

    model_config = {"populate_by_name": True}


class RegionOverviewOutput(BaseModel):
    """Output from region_overview tool."""
    region_key: Annotated[str, Field(alias="regionKey")]
    total_places: Annotated[int, Field(alias="totalPlaces")]
    active_places: Annotated[int, Field(alias="activePlaces")]
    category_stats: Annotated[
        dict[str, CategoryStat],
        Field(alias="categoryStats")
    ] = Field(default_factory=dict)
    avg_overall_rating: Annotated[
        float | None,
        Field(alias="avgOverallRating", description="Weighted average rating across all places")
    ] = Field(default=None)

    model_config = {"populate_by_name": True}


# ============================================================================
# Tool 2: Constraint Research
# ============================================================================

class ConstraintResearchInput(BaseModel):
    """Input for constraint_research tool."""
    mode: str = Field(
        description="Search mode: 'coordinates' or 'text'",
        pattern="^(coordinates|text)$"
    )
    # For coordinates mode
    center_lat: Annotated[
        float | None,
        Field(alias="centerLat", ge=-90, le=90, description="Center latitude")
    ] = Field(default=None)
    center_lng: Annotated[
        float | None,
        Field(alias="centerLng", ge=-180, le=180, description="Center longitude")
    ] = Field(default=None)
    radius_km: Annotated[
        float | None,
        Field(alias="radiusKm", ge=1, le=500, description="Search radius in kilometers")
    ] = Field(default=None)
    # For text mode
    query: Annotated[
        str | None,
        Field(description="Text query for semantic search, e.g. 'khu vực quận 1 Sài Gòn'")
    ] = Field(default=None)
    region_key: Annotated[
        str | None,
        Field(
            default=None,
            alias="regionKey",
            description=(
                "Resolved catalog region used to scope text-mode research. "
                "The free-text query is context only and must not broaden this boundary."
            ),
        ),
    ]
    # Constraints
    budget: Annotated[
        int | None,
        Field(ge=0, description="Total budget in VND")
    ] = Field(default=None)
    duration: Annotated[
        int | None,
        Field(alias="duration", ge=1, le=30, description="Trip duration in days")
    ] = Field(default=None)
    interests: Annotated[
        list[str],
        Field(description="List of interests/categories to filter by")
    ] = Field(default_factory=list)

    model_config = {"extra": "forbid", "populate_by_name": True}

    def model_post_init(self, __context) -> None:
        if self.mode == "coordinates":
            if self.center_lat is None or self.center_lng is None:
                raise ValueError("centerLat and centerLng are required for coordinates mode")
            if self.radius_km is None:
                raise ValueError("radiusKm is required for coordinates mode")
        elif self.mode == "text":
            if not self.query:
                raise ValueError("query is required for text mode")


class ZoneStat(BaseModel):
    """Statistics for a spatial zone."""
    zone_id: Annotated[str, Field(alias="zoneId", description="Zone identifier")]
    center_lat: Annotated[float, Field(alias="centerLat")]
    center_lng: Annotated[float, Field(alias="centerLng")]
    place_count: Annotated[int, Field(alias="placeCount")]
    avg_rating: Annotated[float | None, Field(alias="avgRating")] = Field(default=None)
    avg_daily_cost: Annotated[
        int | None,
        Field(alias="avgDailyCost", description="Estimated daily cost in VND")
    ] = Field(default=None)
    top_categories: Annotated[
        list[str],
        Field(alias="topCategories", description="Top 5 categories in this zone")
    ] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class SpatialStats(BaseModel):
    """Spatial statistics output."""
    zones: list[ZoneStat] = Field(default_factory=list)
    total_zones_in_radius: Annotated[
        int,
        Field(alias="totalZonesInRadius", description="Number of zones found in radius")
    ] = Field(default=0)
    total_places_in_radius: Annotated[
        int,
        Field(alias="totalPlacesInRadius", description="Total places in all zones")
    ] = Field(default=0)

    model_config = {"populate_by_name": True}


class CategoryBudgetStat(BaseModel):
    """Category statistics with budget info."""
    count: int = Field(description="Total places matching this category")
    count_with_price: Annotated[
        int,
        Field(alias="countWithPrice", description="Places with price range data")
    ] = Field(default=0)
    avg_rating: Annotated[float | None, Field(alias="avgRating")] = Field(default=None)
    price_distribution: Annotated[
        dict[str, int],
        Field(alias="priceDistribution", description="Count by price tier")
    ] = Field(default_factory=dict)
    avg_daily_cost: Annotated[
        int | None,
        Field(alias="avgDailyCost", description="Estimated daily cost in VND")
    ] = Field(default=None)

    model_config = {"populate_by_name": True}


class CategoryStatsOutput(BaseModel):
    """Category statistics output for constraint research."""

    food: CategoryBudgetStat | None = None
    cafe: CategoryBudgetStat | None = None
    beach: CategoryBudgetStat | None = None
    nature: CategoryBudgetStat | None = None
    culture: CategoryBudgetStat | None = None
    sightseeing: CategoryBudgetStat | None = None
    attraction: CategoryBudgetStat | None = None
    entertainment: CategoryBudgetStat | None = None
    shopping: CategoryBudgetStat | None = None
    nightlife: CategoryBudgetStat | None = None
    wellness: CategoryBudgetStat | None = None
    accommodation: CategoryBudgetStat | None = None
    transport: CategoryBudgetStat | None = None
    other: CategoryBudgetStat | None = None

    model_config = {"extra": "forbid"}


class BudgetCompatibility(BaseModel):
    """Budget compatibility analysis."""
    within_budget: Annotated[
        bool,
        Field(alias="withinBudget", description="Whether the estimated cost fits within budget")
    ]
    estimated_total_cost: Annotated[
        int | None,
        Field(alias="estimatedTotalCost", description="Estimated total cost in VND")
    ] = Field(default=None)
    left_over: Annotated[
        int | None,
        Field(alias="leftOver", description="Remaining budget after estimated cost")
    ] = Field(default=None)
    daily_budget: Annotated[
        int | None,
        Field(alias="dailyBudget", description="Per-day budget if duration specified")
    ] = Field(default=None)

    model_config = {"populate_by_name": True}


class ConstraintResearchOutput(BaseModel):
    """Output from constraint_research tool."""
    spatial_stats: Annotated[SpatialStats, Field(alias="spatialStats")]
    category_stats: Annotated[CategoryStatsOutput, Field(alias="categoryStats")]
    budget_compatibility: Annotated[
        BudgetCompatibility | None,
        Field(alias="budgetCompatibility")
    ] = Field(default=None)

    model_config = {"populate_by_name": True}


# ============================================================================
# Tool 3: Festival Discovery
# ============================================================================

class FestivalDiscoveryInput(BaseModel):
    """Input for festival_discovery tool."""
    month: Annotated[
        str | None,
        Field(
            description="Month filter in Vietnamese format, e.g. 'tháng 4' or 'tháng 4/2026'. None = all festivals"
        )
    ] = Field(default=None)
    region_key: Annotated[
        str | None,
        Field(
            default=None,
            alias="regionKey",
            description="Resolved destination region used to exclude unrelated local events",
        ),
    ]

    model_config = {"extra": "forbid", "populate_by_name": True}


class Festival(BaseModel):
    """Festival/holiday information."""
    name: str = Field(description="Festival name")
    date: str = Field(description="Date description, e.g. '10/3 âm lịch' or '30/4 - 1/5'")
    region_keys: Annotated[
        list[str],
        Field(alias="regionKeys", description="List of region keys where festival is celebrated")
    ] = Field(default_factory=list)
    region_names: Annotated[
        list[str],
        Field(alias="regionNames", description="Human-readable region names")
    ] = Field(default_factory=list)
    scale: str = Field(
        description="Scale: 'quoc-gia' (national), 'vung' (regional), 'dia-phuong' (local)"
    )
    activities: list[str] = Field(
        description="Typical activities at this festival",
        default_factory=list
    )
    description: str | None = Field(default=None)

    model_config = {"populate_by_name": True}


class MonthFestivals(BaseModel):
    """Festivals grouped by month."""
    festivals: list[Festival] = Field(default_factory=list)


class FestivalDiscoveryOutput(BaseModel):
    """Output from festival_discovery tool."""
    festivals: list[Festival] = Field(
        description="List of festivals, optionally filtered by month"
    )
    by_month: Annotated[
        dict[str, list[str]],
        Field(
            alias="byMonth",
            description="Festivals indexed by month for quick lookup"
        )
    ] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
