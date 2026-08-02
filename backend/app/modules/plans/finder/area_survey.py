"""Minimal regional planning profile backed by persisted catalog statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any, Protocol

from app.modules.places.auto_statistics.service import PlannerRegionStatisticsResult
from app.modules.plans.finder.place_tool import (
    FinderPlace,
    FinderPlaceTool,
    place_category,
)
from app.modules.plans.planner.opening_hours_parser import (
    extract_time_intervals,
    is_24_hours,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AreaProfile:
    """Only the regional signals currently consumed by Finder."""

    region_key: str
    distribution: dict[str, int]
    bbox: tuple[float, float, float, float] | None
    estimated_walkability: str
    typical_hours: str


class AreaProfileProvider(Protocol):
    def get(self, region_key: str) -> AreaProfile: ...


class RegionStatisticsProvider(Protocol):
    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> PlannerRegionStatisticsResult: ...


class StatisticsAreaProfileProvider:
    """Read the persisted region snapshot, with catalog sampling as fallback."""

    WALKABILITY_HIGH_KM = 0.5
    WALKABILITY_MEDIUM_KM = 1.0

    def __init__(
        self,
        place_tool: FinderPlaceTool,
        statistics_provider: RegionStatisticsProvider | None = None,
        *,
        max_fallback_places: int = 500,
    ) -> None:
        self.place_tool = place_tool
        self.statistics_provider = statistics_provider
        self.max_fallback_places = max_fallback_places

    def get(self, region_key: str) -> AreaProfile:
        if self.statistics_provider is not None:
            try:
                profile = self._from_statistics(region_key)
                if profile is not None:
                    return profile
            except (KeyError, TypeError, ValueError, RuntimeError):
                logger.warning(
                    "Region statistics unavailable for %s; sampling catalog.",
                    region_key,
                    exc_info=True,
                )
        return self._from_catalog(region_key)

    def _from_statistics(self, region_key: str) -> AreaProfile | None:
        provider = self.statistics_provider
        if provider is None:
            return None
        result = provider.get_for_planner(region_key)
        metrics = next(
            (
                item
                for item in result.regions
                if item.get("regionKey") == region_key
            ),
            None,
        )
        if not isinstance(metrics, dict):
            return None

        eligible = metrics.get("plannerEligible")
        source = eligible if isinstance(eligible, dict) else metrics
        distribution = _distribution_from_type_counts(source.get("countsByType"))
        bbox = _bbox_from_statistics(source.get("geographicSummary"))
        typical_hours = _typical_hours_from_coverage(source.get("timeOfDayCoverage"))
        return AreaProfile(
            region_key=region_key,
            distribution=distribution,
            bbox=bbox,
            # Statistics currently stores bbox/centroid but no defensible
            # walkability metric. Unknown avoids presenting a fabricated one.
            estimated_walkability="unknown",
            typical_hours=typical_hours,
        )

    def _from_catalog(self, region_key: str) -> AreaProfile:
        list_region = getattr(self.place_tool, "list_region", None)
        if list_region is not None:
            places = list_region(region_key, limit=self.max_fallback_places)
        else:
            places = self.place_tool.search(
                region_key=region_key,
                target_tags=[],
                excluded_place_ids=set(),
                limit=self.max_fallback_places,
            )

        distribution: dict[str, int] = {}
        for place in places:
            category = place_category(place) or "other"
            distribution[category] = distribution.get(category, 0) + 1

        coordinates = [
            (place.latitude, place.longitude)
            for place in places
            if place.latitude is not None and place.longitude is not None
        ]
        average_distance = _average_pair_distance(coordinates)
        if len(coordinates) < 2:
            walkability = "unknown"
        elif average_distance <= self.WALKABILITY_HIGH_KM:
            walkability = "high"
        elif average_distance <= self.WALKABILITY_MEDIUM_KM:
            walkability = "medium"
        else:
            walkability = "low"

        return AreaProfile(
            region_key=region_key,
            distribution=distribution,
            bbox=_bbox_from_coordinates(coordinates),
            estimated_walkability=walkability,
            typical_hours=_typical_hours_from_places(places),
        )


def _distribution_from_type_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    distribution: dict[str, int] = {}
    for raw_type, raw_count in value.items():
        if not isinstance(raw_type, str) or not isinstance(raw_count, int):
            continue
        probe = FinderPlace(
            name=raw_type,
            placeType=raw_type,
            regionKey="vn,statistics",
        )
        category = place_category(probe) or "other"
        distribution[category] = distribution.get(category, 0) + raw_count
    return distribution


def _bbox_from_statistics(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, dict):
        return None
    bbox = value.get("boundingBox")
    if not isinstance(bbox, dict):
        return None
    try:
        return (
            float(bbox["minLatitude"]),
            float(bbox["minLongitude"]),
            float(bbox["maxLatitude"]),
            float(bbox["maxLongitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _typical_hours_from_coverage(value: Any) -> str:
    if not isinstance(value, dict):
        return "all_day"
    known = int(value.get("placesWithKnownHours") or 0)
    if known <= 0:
        return "all_day"
    morning_ratio = int(value.get("morning") or 0) / known
    evening_ratio = int(value.get("evening") or 0) / known
    if morning_ratio > 0.4:
        return "morning_focused"
    if evening_ratio > 0.4:
        return "evening_focused"
    return "all_day"


def _typical_hours_from_places(places: list[FinderPlace]) -> str:
    known = 0
    early = 0
    late = 0
    for place in places:
        if not place.opening_hours:
            continue
        known += 1
        if is_24_hours(place.opening_hours):
            early += 1
            late += 1
            continue
        intervals = extract_time_intervals(place.opening_hours)
        if any(0 <= start <= 8 * 60 for start, _ in intervals):
            early += 1
        if any(_is_late_close(end) for _, end in intervals):
            late += 1
    if known == 0:
        return "all_day"
    if early / known > 0.4:
        return "morning_focused"
    if late / known > 0.4:
        return "evening_focused"
    return "all_day"


def _is_late_close(value: int) -> bool:
    normalized = value if value <= 24 * 60 else value - 24 * 60
    return normalized >= 21 * 60


def _average_pair_distance(coordinates: list[tuple[float, float]]) -> float:
    if len(coordinates) < 2:
        return 0.0
    sample_size = min(50, len(coordinates))
    if sample_size == len(coordinates):
        sampled = coordinates
    else:
        indexes = [
            round(index * (len(coordinates) - 1) / (sample_size - 1))
            for index in range(sample_size)
        ]
        sampled = [coordinates[index] for index in indexes]
    distances = [
        _haversine_km(sampled[left], sampled[right])
        for left in range(len(sampled))
        for right in range(left + 1, len(sampled))
    ]
    return sum(distances) / len(distances)


def _haversine_km(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> float:
    lat1, lon1 = map(radians, origin)
    lat2, lon2 = map(radians, destination)
    delta_latitude = lat2 - lat1
    delta_longitude = lon2 - lon1
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_longitude / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(value))


def _bbox_from_coordinates(
    coordinates: list[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    if not coordinates:
        return None
    latitudes = [coordinate[0] for coordinate in coordinates]
    longitudes = [coordinate[1] for coordinate in coordinates]
    return (
        min(latitudes),
        min(longitudes),
        max(latitudes),
        max(longitudes),
    )
