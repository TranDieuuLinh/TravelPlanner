from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Protocol

from app.modules.places.model import Place
from app.modules.plans.dto.agent_contracts import (
    TourismZoneAnchor,
    TourismZoneEvidence,
)
from app.modules.plans.planner.place_metadata import (
    read_place_group,
    read_rating,
    read_review_count,
)
from app.modules.plans.planner.research_tool import (
    CAPABILITY_ALIASES,
    CAPABILITY_CATEGORY,
    canonical_capability,
    place_supports_capability,
)
from app.modules.plans.knowledge_graph import (
    TravelKnowledgeSearchTool,
    get_default_travel_knowledge_tool,
)


DEFAULT_ZONE_RADIUS_METERS = 2_500
MAX_TOURISM_ZONES = 12

_FOOD_CAPABILITIES = {"coffee", "food", "seafood"}
_GENERIC_ANCHOR_MARKERS = {
    "art_gallery",
    "cultural_center",
    "historical_landmark",
    "historical_place",
    "memorial",
    "monument",
    "museum",
    "national_park",
    "nature_reserve",
    "park",
    "scenic_spot",
    "tourist_attraction",
}


class TourismZonePlaceRepository(Protocol):
    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Place]: ...


class TourismZoneResearchTool(Protocol):
    def research(
        self,
        *,
        root_region_key: str,
        interests: list[str],
    ) -> list[TourismZoneEvidence]: ...


class EmptyTourismZoneResearchTool:
    def research(
        self,
        *,
        root_region_key: str,
        interests: list[str],
    ) -> list[TourismZoneEvidence]:
        return []


class RepositoryTourismZoneResearchTool:
    """Build compact, database-backed tourism zones around strong anchors."""

    def __init__(
        self,
        repository: TourismZonePlaceRepository,
        *,
        radius_meters: int = DEFAULT_ZONE_RADIUS_METERS,
        max_zones: int = MAX_TOURISM_ZONES,
        knowledge_tool: TravelKnowledgeSearchTool | None = None,
    ) -> None:
        self.repository = repository
        self.radius_meters = radius_meters
        self.max_zones = max_zones
        self.knowledge_tool = knowledge_tool or get_default_travel_knowledge_tool()

    def research(
        self,
        *,
        root_region_key: str,
        interests: list[str],
    ) -> list[TourismZoneEvidence]:
        places = self.repository.list_active_for_planner_research(
            root_region_key,
            limit=30_000,
        )
        places_with_coordinates = [
            place
            for place in places
            if place.latitude is not None and place.longitude is not None
        ]
        if not places_with_coordinates:
            return []

        capabilities_by_id = {
            str(place.id): self._capabilities([place])
            for place in places_with_coordinates
        }

        requested = {
            canonical_capability(interest)
            for interest in interests
            if canonical_capability(interest) in CAPABILITY_ALIASES
        }
        food_focused = bool(requested) and requested.issubset(_FOOD_CAPABILITIES)
        area_expansion = self.knowledge_tool.expand(
            interests,
            region_key=root_region_key,
        )
        preferred_region_keys = set(area_expansion.region_keys)
        grouped: dict[str, list[Place]] = defaultdict(list)
        for place in places_with_coordinates:
            grouped[place.region_key].append(place)

        anchor_specs: list[tuple[Place, str]] = []
        for region_key, regional_places in grouped.items():
            anchors = [
                place
                for place in regional_places
                if self._eligible_anchor(
                    place,
                    requested=requested,
                    food_focused=food_focused,
                    capabilities=capabilities_by_id[str(place.id)],
                )
            ]
            if not anchors:
                continue
            anchors.sort(
                key=lambda place: (
                    0
                    if self._in_preferred_region(place.region_key, preferred_region_keys)
                    else 1,
                    -self._popularity(place),
                    place.name.casefold(),
                )
            )
            chosen_anchors: list[Place] = []
            chosen_categories: set[str] = set()
            for anchor in anchors:
                category = self._anchor_category(
                    anchor,
                    self._capabilities([anchor]),
                )
                if category in chosen_categories:
                    continue
                chosen_anchors.append(anchor)
                chosen_categories.add(category)
                if len(chosen_anchors) >= 2:
                    break
            anchor_specs.extend((anchor, region_key) for anchor in chosen_anchors)

        # Building a zone scans nearby places and derives capability coverage.
        # Shortlist anchors first: doing that expensive work for every small
        # administrative region made full-Hanoi research effectively
        # quadratic after the catalogue grew beyond 20k places.
        anchor_specs.sort(
            key=lambda item: (
                0
                if self._in_preferred_region(item[0].region_key, preferred_region_keys)
                else 1,
                -self._popularity(item[0]),
                item[0].name.casefold(),
            )
        )
        shortlist_size = max(self.max_zones + 4, 16)
        zones = [
            self._build_zone(
                anchor,
                region_key=region_key,
                places=places_with_coordinates,
                capabilities_by_id=capabilities_by_id,
            )
            for anchor, region_key in anchor_specs[:shortlist_size]
        ]

        zones.sort(
            key=lambda zone: (
                0
                if self._in_preferred_region(zone.region_key, preferred_region_keys)
                else 1,
                (
                    0
                    if (
                        zone.anchor_places[0].category == "food_drink"
                    ) == food_focused
                    else 1
                ),
                -len(set(zone.capabilities).intersection(requested)),
                -zone.popularity_score,
                -zone.compactness_score,
                -zone.place_count,
                zone.region_key,
            )
        )
        return zones[: self.max_zones]

    @staticmethod
    def _in_preferred_region(
        region_key: str,
        preferred_region_keys: set[str],
    ) -> bool:
        return any(
            region_key == preferred
            or region_key.startswith(f"{preferred},")
            for preferred in preferred_region_keys
        )

    def _build_zone(
        self,
        anchor: Place,
        *,
        region_key: str,
        places: list[Place],
        capabilities_by_id: dict[str, set[str]],
    ) -> TourismZoneEvidence:
        center = self._coordinates(anchor)
        nearby = [
            place
            for place in places
            if self._distance_meters(center, self._coordinates(place))
            <= self.radius_meters
        ]
        capabilities = self._capabilities(
            nearby,
            capabilities_by_id=capabilities_by_id,
        )
        coverage = self._category_coverage(
            nearby,
            capabilities_by_id=capabilities_by_id,
        )
        primary_categories = sorted(
            {
                CAPABILITY_CATEGORY[capability]
                for capability in capabilities
                if capability in CAPABILITY_CATEGORY
            }
        )
        anchor_category = self._anchor_category(
            anchor,
            capabilities_by_id[str(anchor.id)],
        )
        average_distance = sum(
            self._distance_meters(center, self._coordinates(place))
            for place in nearby
        ) / len(nearby)
        compactness = max(
            0.0,
            min(1.0, 1.0 - average_distance / self.radius_meters),
        )
        return TourismZoneEvidence(
            zoneId=f"{_slug(region_key)}--{_slug(str(anchor.id))}",
            regionKey=region_key,
            centerLatitude=center[0],
            centerLongitude=center[1],
            radiusMeters=self.radius_meters,
            capabilities=sorted(capabilities),
            primaryCategories=primary_categories,
            categoryCoverage=coverage,
            anchorPlaces=[
                TourismZoneAnchor(
                    placeId=str(anchor.id),
                    name=anchor.name,
                    category=anchor_category,
                    latitude=center[0],
                    longitude=center[1],
                    rating=read_rating(anchor),
                    reviewCount=read_review_count(anchor),
                    popularityScore=round(self._popularity(anchor), 4),
                )
            ],
            placeCount=len(nearby),
            compactnessScore=round(compactness, 4),
            popularityScore=round(self._popularity(anchor), 4),
        )

    def _eligible_anchor(
        self,
        place: Place,
        *,
        requested: set[str],
        food_focused: bool,
        capabilities: set[str] | None = None,
    ) -> bool:
        capabilities = capabilities or self._capabilities([place])
        if requested and not requested.intersection(capabilities):
            return False
        anchor_category = self._anchor_category(place, capabilities)
        if (
            anchor_category == "food_drink"
            and not requested.intersection(_FOOD_CAPABILITIES)
        ):
            return False
        if food_focused:
            return bool(capabilities.intersection(_FOOD_CAPABILITIES))
        if capabilities.difference(_FOOD_CAPABILITIES):
            return True
        if requested.intersection(_FOOD_CAPABILITIES):
            return bool(capabilities.intersection(_FOOD_CAPABILITIES))
        return _normalized_label(place.place_type) in _GENERIC_ANCHOR_MARKERS

    @staticmethod
    def _capabilities(
        places: list[Place],
        *,
        capabilities_by_id: dict[str, set[str]] | None = None,
    ) -> set[str]:
        if capabilities_by_id is not None:
            return {
                capability
                for place in places
                for capability in capabilities_by_id.get(str(place.id), set())
            }
        return {
            capability
            for capability in CAPABILITY_ALIASES
            if any(place_supports_capability(place, capability) for place in places)
        }

    @staticmethod
    def _category_coverage(
        places: list[Place],
        *,
        capabilities_by_id: dict[str, set[str]] | None = None,
    ) -> dict[str, int]:
        coverage: dict[str, int] = defaultdict(int)
        for place in places:
            categories = {
                CAPABILITY_CATEGORY[capability]
                for capability in (
                    capabilities_by_id.get(str(place.id), set())
                    if capabilities_by_id is not None
                    else CAPABILITY_ALIASES
                )
                if capability in CAPABILITY_CATEGORY
                and (
                    capabilities_by_id is not None
                    or place_supports_capability(place, capability)
                )
            }
            for category in categories:
                coverage[category] += 1
        return dict(sorted(coverage.items()))

    @staticmethod
    def _anchor_category(place: Place, capabilities: set[str]) -> str:
        place_type = _normalized_label(place.place_type)
        place_group = _normalized_label(read_place_group(place) or "")
        if place_group == "food_drink" or any(
            marker in place_type
            for marker in (
                "bakery",
                "cafe",
                "coffee",
                "food",
                "restaurant",
            )
        ):
            return "food_drink"
        if any(marker in place_type for marker in ("beach", "nature", "park")):
            return "nature"
        if place_type in _GENERIC_ANCHOR_MARKERS:
            return "attraction"
        categories = [
            CAPABILITY_CATEGORY[capability]
            for capability in sorted(capabilities)
            if capability in CAPABILITY_CATEGORY
        ]
        return categories[0] if categories else "attraction"

    @staticmethod
    def _popularity(place: Place) -> float:
        rating = max(0.0, min(read_rating(place) or 0.0, 5.0)) / 5.0
        reviews = max(0, read_review_count(place))
        review_strength = min(1.0, math.log10(reviews + 1) / 4.0)
        return rating * 0.6 + review_strength * 0.4

    @staticmethod
    def _coordinates(place: Place) -> tuple[float, float]:
        return float(place.latitude), float(place.longitude)

    @staticmethod
    def _distance_meters(
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        left_latitude, left_longitude = map(math.radians, left)
        right_latitude, right_longitude = map(math.radians, right)
        latitude_delta = right_latitude - left_latitude
        longitude_delta = right_longitude - left_longitude
        value = (
            math.sin(latitude_delta / 2) ** 2
            + math.cos(left_latitude)
            * math.cos(right_latitude)
            * math.sin(longitude_delta / 2) ** 2
        )
        return 6_371_000 * 2 * math.asin(math.sqrt(value))


def _normalized_label(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFD",
        value.strip().casefold().replace("đ", "d"),
    )
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "_", without_marks).strip("_")


def _slug(value: str) -> str:
    return _normalized_label(value).replace("_", "-")
