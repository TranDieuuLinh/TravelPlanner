from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Protocol

from app.modules.places.model import Place
from app.modules.plans.dto.agent_contracts import (
    PlannerCapabilityEvidence,
    PlannerNearbyRegionEvidence,
    PlannerResearchDraft,
    PlannerVerifiedResearch,
)
from app.modules.plans.planner.place_metadata import read_place_group, read_tags


CAPABILITY_ALIASES: dict[str, set[str]] = {
    "beach": {"beach", "coast", "seaside", "swimming", "bien"},
    "seafood": {"seafood", "local_seafood", "hai_san"},
    "mountain": {"mountain", "peak", "summit", "nui"},
    "hiking": {"hiking", "trekking", "trail", "mountain", "leo_nui"},
    "food": {"food", "restaurant", "local_food", "street_food", "am_thuc"},
    "coffee": {"coffee", "cafe", "coffee_shop"},
    "culture": {"culture", "museum", "heritage", "historic"},
    "nature": {"nature", "park", "garden", "waterfall", "forest"},
    "nightlife": {"nightlife", "bar", "pub", "nightclub"},
    "camping": {"camping", "campsite"},
    "shopping": {"shopping", "market", "mall"},
    "wellness": {"wellness", "spa", "hot_spring"},
}

CAPABILITY_SYNONYMS = {
    "bien": "beach",
    "tam_bien": "beach",
    "hai_san": "seafood",
    "nui": "mountain",
    "leo_nui": "hiking",
    "trekking": "hiking",
    "am_thuc": "food",
    "ca_phe": "coffee",
    "van_hoa": "culture",
    "thien_nhien": "nature",
    "cam_trai": "camping",
}


class PlannerResearchPlaceRepository(Protocol):
    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Place]: ...


class PlannerResearchTool(Protocol):
    def verify(
        self,
        draft: PlannerResearchDraft,
        *,
        root_region_key: str,
    ) -> PlannerVerifiedResearch: ...


class EmptyPlannerResearchTool:
    def verify(
        self,
        draft: PlannerResearchDraft,
        *,
        root_region_key: str,
    ) -> PlannerVerifiedResearch:
        return PlannerVerifiedResearch(
            warnings=[
                "Planner research database tool is not configured; creative "
                "themes cannot be verified beyond the supplied region snapshot."
            ]
        )


class RepositoryPlannerResearchTool:
    def __init__(
        self,
        repository: PlannerResearchPlaceRepository,
        *,
        sample_limit: int = 3,
        nearby_limit: int = 8,
    ) -> None:
        self.repository = repository
        self.sample_limit = sample_limit
        self.nearby_limit = nearby_limit

    def verify(
        self,
        draft: PlannerResearchDraft,
        *,
        root_region_key: str,
    ) -> PlannerVerifiedResearch:
        local_places = self.repository.list_active_for_planner_research(
            root_region_key
        )
        capability_evidence: list[PlannerCapabilityEvidence] = []
        warnings: list[str] = []

        for query in draft.theme_queries:
            scope = query.preferred_region_key or root_region_key
            scoped_places = (
                local_places
                if scope == root_region_key
                else self.repository.list_active_for_planner_research(scope)
            )
            for raw_capability in query.capabilities:
                capability = canonical_capability(raw_capability)
                matches = [
                    place
                    for place in scoped_places
                    if place_supports_capability(place, capability)
                ]
                supported = bool(matches)
                capability_evidence.append(
                    PlannerCapabilityEvidence(
                        theme=query.theme,
                        capability=capability,
                        supported=supported,
                        activePlaceCount=len(matches),
                        regionKeys=_top_region_keys(matches),
                        samplePlaces=[
                            _place_evidence(place)
                            for place in matches[: self.sample_limit]
                        ],
                        confidence=_evidence_confidence(len(matches)),
                    )
                )
                if not supported:
                    warnings.append(
                        f"No active Place evidence for capability "
                        f"'{capability}' in {scope}."
                    )

        nearby_regions: list[PlannerNearbyRegionEvidence] = []
        if draft.expand_beyond_root:
            nearby_regions = self._find_nearby_regions(
                root_region_key=root_region_key,
                capabilities=draft.nearby_capabilities,
                max_distance_km=draft.max_distance_km,
            )
            if not nearby_regions:
                warnings.append(
                    "No database-backed nearby region matched the requested "
                    "capabilities and distance."
                )

        return PlannerVerifiedResearch(
            capabilityEvidence=capability_evidence,
            nearbyRegions=nearby_regions,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _find_nearby_regions(
        self,
        *,
        root_region_key: str,
        capabilities: list[str],
        max_distance_km: float,
    ) -> list[PlannerNearbyRegionEvidence]:
        origin_places = self.repository.list_active_for_planner_research(
            root_region_key
        )
        origin_centroid = _centroid(origin_places)
        if origin_centroid is None:
            return []

        canonical_capabilities = [
            canonical_capability(capability)
            for capability in capabilities
        ]
        origin_depth = len(root_region_key.split(","))
        grouped: dict[str, list[Place]] = defaultdict(list)
        for place in self.repository.list_active_for_planner_research():
            if _in_region(place.region_key, root_region_key):
                continue
            candidate_key = _region_at_depth(place.region_key, origin_depth)
            if candidate_key:
                grouped[candidate_key].append(place)

        results: list[PlannerNearbyRegionEvidence] = []
        for region_key, places in grouped.items():
            candidate_centroid = _centroid(places)
            if candidate_centroid is None:
                continue
            distance_km = _haversine_km(origin_centroid, candidate_centroid)
            if distance_km > max_distance_km:
                continue

            matching_places = [
                place
                for place in places
                if not canonical_capabilities
                or any(
                    place_supports_capability(place, capability)
                    for capability in canonical_capabilities
                )
            ]
            if not matching_places:
                continue
            matching_capabilities = [
                capability
                for capability in canonical_capabilities
                if any(
                    place_supports_capability(place, capability)
                    for place in matching_places
                )
            ]
            results.append(
                PlannerNearbyRegionEvidence(
                    regionKey=region_key,
                    distanceKm=round(distance_km, 1),
                    activePlaceCount=len(matching_places),
                    matchingCapabilities=matching_capabilities,
                    samplePlaces=[
                        _place_evidence(place)
                        for place in matching_places[: self.sample_limit]
                    ],
                )
            )

        results.sort(
            key=lambda item: (
                -len(item.matching_capabilities),
                -item.active_place_count,
                item.distance_km,
                item.region_key,
            )
        )
        return results[: self.nearby_limit]


def canonical_capability(value: str) -> str:
    normalized = _normalized_label(value)
    return CAPABILITY_SYNONYMS.get(normalized, normalized)


def place_supports_capability(place: Place, capability: str) -> bool:
    aliases = CAPABILITY_ALIASES.get(capability, {capability})
    tags = read_tags(place)
    place_group = read_place_group(place) or ""
    raw_values = [
        place.place_type,
        place.name,
        *tags,
        place_group,
    ]
    metadata = place.metadata_json or {}
    indoor_outdoor = metadata.get("indoorOutdoor") or metadata.get("indoor_outdoor")
    if indoor_outdoor:
        raw_values.append(str(indoor_outdoor))
    normalized_values = {
        _normalized_label(str(value))
        for value in raw_values
        if value
    }
    return any(
        _contains_label(value, alias)
        for value in normalized_values
        for alias in aliases
    )


def _place_evidence(place: Place) -> dict[str, object]:
    tags = read_tags(place)[:8]
    return {
        "placeId": place.id,
        "name": place.name,
        "regionKey": place.region_key,
        "placeType": place.place_type,
        "tags": [str(tag) for tag in tags],
        "placeGroup": read_place_group(place),
        "dataConfidence": place.data_confidence,
    }


def _top_region_keys(places: list[Place]) -> list[str]:
    counts: dict[str, int] = {}
    for place in places:
        counts[place.region_key] = counts.get(place.region_key, 0) + 1
    return [
        region_key
        for region_key, _ in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:8]
    ]


def _evidence_confidence(count: int) -> str:
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    if count == 1:
        return "low"
    return "none"


def _normalized_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "_", without_marks).strip("_")


def _contains_label(value: str, label: str) -> bool:
    return label == value or f"_{label}_" in f"_{value}_"


def _in_region(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(f"{root},")


def _region_at_depth(region_key: str, depth: int) -> str | None:
    parts = [part for part in region_key.split(",") if part]
    if len(parts) < 2:
        return None
    return ",".join(parts[: min(depth, len(parts))])


def _centroid(places: list[Place]) -> tuple[float, float] | None:
    coordinates = [
        (float(place.latitude), float(place.longitude))
        for place in places
        if place.latitude is not None and place.longitude is not None
    ]
    if not coordinates:
        return None
    return (
        sum(latitude for latitude, _ in coordinates) / len(coordinates),
        sum(longitude for _, longitude in coordinates) / len(coordinates),
    )


def _haversine_km(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    earth_radius_km = 6371.0
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
    return earth_radius_km * 2 * math.asin(math.sqrt(value))
