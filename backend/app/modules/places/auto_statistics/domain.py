from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable


ALGORITHM_VERSION = "auto_statistics_v3_0"

TIME_SLOTS: dict[str, tuple[int, int]] = {
    "morning": (5 * 60, 11 * 60),
    "lunch": (11 * 60, 14 * 60),
    "afternoon": (14 * 60, 18 * 60),
    "evening": (18 * 60, 24 * 60),
}

TAG_ALIASES = {
    "restaurant": "food",
    "fast_food": "food",
    "fastfood": "food",
    "food_court": "food",
    "food_drink": "food",
    "local_food": "food",
    "do_an_vat": "food",
    "o_an_vat": "food",
    "bakery": "food",
    "cafe": "coffee",
    "coffee_shop": "coffee",
    "historic": "culture",
    "heritage": "culture",
    "museum": "culture",
    "gallery": "culture",
    "artwork": "culture",
    "memorial": "culture",
    "archaeological_site": "culture",
    "attraction": "sightseeing",
    "viewpoint": "sightseeing",
    "park": "nature",
    "garden": "nature",
    "natural": "nature",
    "beach": "nature",
    "waterfall": "nature",
    "water": "nature",
    "marketplace": "shopping",
    "market": "shopping",
    "mall": "shopping",
    "clothes": "shopping",
    "supermarket": "shopping",
    "convenience": "shopping",
    "bar": "nightlife",
    "pub": "nightlife",
    "nightclub": "nightlife",
    "hotel": "accommodation",
    "hostel": "accommodation",
    "motel": "accommodation",
    "cinema": "entertainment",
    "theatre": "entertainment",
    "amusement_arcade": "entertainment",
    "station": "transport",
    "airport": "transport",
    "aerodrome": "transport",
}


@dataclass(frozen=True)
class PlaceStatisticsRecord:
    id: str
    region_key: str
    place_type: str
    status: str
    latitude: float | None
    longitude: float | None
    opening_hours: list[dict[str, Any]]
    typical_duration_minutes: int | None
    data_confidence: str
    source_fetched_at: datetime | None
    metadata: dict[str, Any]


class RegionAccumulator:
    def __init__(self, region_key: str) -> None:
        self.region_key = region_key
        self.place_count = 0
        self.direct_place_count = 0
        self.active_place_count = 0
        self.counts_by_type: dict[str, int] = {}
        self.counts_by_status: dict[str, int] = {}
        self.slot_place_counts = {slot: 0 for slot in TIME_SLOTS}
        self.known_hours_count = 0
        self.duration_by_type: dict[str, list[int]] = {}
        self.tag_counts: dict[str, int] = {}
        self.place_group_counts: dict[str, int] = {}
        self.tag_slot_counts: dict[str, dict[str, int]] = {}
        self.duration_by_tag: dict[str, list[int]] = {}
        self.indoor_outdoor_counts: dict[str, int] = {}
        self.weather_sensitivity_counts: dict[str, int] = {}
        self.booking_requirement_counts = {
            "required": 0,
            "notRequired": 0,
            "unknown": 0,
        }
        self.missing_coordinates = 0
        self.missing_opening_hours = 0
        self.missing_source_fetched_at = 0
        self.stale_operational_data = 0
        self.mock_opening_hours = 0
        self.places_with_any_price = 0
        self.places_with_verified_price = 0
        self.places_with_only_mock_prices = 0
        self.confidence_counts: dict[str, int] = {}
        self.coordinates: list[tuple[float, float]] = []

    def add(
        self,
        place: PlaceStatisticsRecord,
        stale_before: datetime,
        *,
        direct: bool = False,
    ) -> None:
        self.place_count += 1
        if direct:
            self.direct_place_count += 1
        if place.status == "active":
            self.active_place_count += 1
        _increment(self.counts_by_type, place.place_type or "unknown")
        _increment(self.counts_by_status, place.status or "unverified")
        _increment(self.confidence_counts, place.data_confidence or "low")

        if place.latitude is None or place.longitude is None:
            self.missing_coordinates += 1
        else:
            self.coordinates.append((place.latitude, place.longitude))

        covered_slots: set[str] = set()
        if not place.opening_hours:
            self.missing_opening_hours += 1
        else:
            self.known_hours_count += 1
            covered_slots = _covered_time_slots(place.opening_hours)
            for slot in covered_slots:
                self.slot_place_counts[slot] += 1
            if any(_is_mock(hour) for hour in place.opening_hours):
                self.mock_opening_hours += 1

        if place.source_fetched_at is None:
            self.missing_source_fetched_at += 1
        elif place.source_fetched_at < stale_before:
            self.stale_operational_data += 1

        if place.typical_duration_minutes is not None:
            self.duration_by_type.setdefault(place.place_type or "unknown", []).append(
                place.typical_duration_minutes
            )

        tags = _normalized_tags(place.metadata.get("tags", []))
        for tag in tags:
            _increment(self.tag_counts, tag)
            slot_counts = self.tag_slot_counts.setdefault(
                tag,
                {slot: 0 for slot in TIME_SLOTS},
            )
            for slot in covered_slots:
                slot_counts[slot] += 1
            if place.typical_duration_minutes is not None:
                self.duration_by_tag.setdefault(tag, []).append(
                    place.typical_duration_minutes
                )

        place_group = _normalized_label(place.metadata.get("placeGroup"))
        if place_group:
            _increment(self.place_group_counts, place_group)

        indoor_outdoor = _normalized_label(place.metadata.get("indoorOutdoor"))
        _increment(self.indoor_outdoor_counts, indoor_outdoor or "unknown")

        weather_sensitivity = _normalized_label(
            place.metadata.get("weatherSensitivity")
        )
        _increment(
            self.weather_sensitivity_counts,
            weather_sensitivity or "unknown",
        )

        booking_required = place.metadata.get("bookingRequired")
        if booking_required is True:
            self.booking_requirement_counts["required"] += 1
        elif booking_required is False:
            self.booking_requirement_counts["notRequired"] += 1
        else:
            self.booking_requirement_counts["unknown"] += 1

        prices = place.metadata.get("prices", [])
        if prices:
            self.places_with_any_price += 1
            has_verified = any(not price.get("isMock", False) for price in prices)
            if has_verified:
                self.places_with_verified_price += 1
            else:
                self.places_with_only_mock_prices += 1

    def to_dict(self) -> dict[str, Any]:
        geographic_summary: dict[str, Any] = {
            "coordinatePlaceCount": len(self.coordinates),
            "centroid": None,
            "boundingBox": None,
        }
        if self.coordinates:
            latitudes = [coordinate[0] for coordinate in self.coordinates]
            longitudes = [coordinate[1] for coordinate in self.coordinates]
            geographic_summary["centroid"] = {
                "latitude": round(sum(latitudes) / len(latitudes), 7),
                "longitude": round(sum(longitudes) / len(longitudes), 7),
            }
            geographic_summary["boundingBox"] = {
                "minLatitude": min(latitudes),
                "minLongitude": min(longitudes),
                "maxLatitude": max(latitudes),
                "maxLongitude": max(longitudes),
            }

        duration_summary = {
            place_type: {
                "medianMinutes": int(median(values)),
                "sampleSize": len(values),
            }
            for place_type, values in sorted(self.duration_by_type.items())
        }
        tag_duration_summary = {
            tag: {
                "medianMinutes": int(median(values)),
                "sampleSize": len(values),
            }
            for tag, values in sorted(self.duration_by_tag.items())
        }

        return {
            "regionKey": self.region_key,
            "placeCount": self.place_count,
            "directPlaceCount": self.direct_place_count,
            "activePlaceCount": self.active_place_count,
            "countsByType": dict(sorted(self.counts_by_type.items())),
            "countsByStatus": dict(sorted(self.counts_by_status.items())),
            "timeOfDayCoverage": {
                **self.slot_place_counts,
                "placesWithKnownHours": self.known_hours_count,
            },
            "typicalDurationByType": duration_summary,
            "tagCounts": dict(sorted(self.tag_counts.items())),
            "placeGroupCounts": dict(sorted(self.place_group_counts.items())),
            "tagTimeCoverage": {
                tag: counts
                for tag, counts in sorted(self.tag_slot_counts.items())
            },
            "tagDurationProfile": tag_duration_summary,
            "indoorOutdoorMix": dict(sorted(self.indoor_outdoor_counts.items())),
            "weatherSensitivityCounts": dict(
                sorted(self.weather_sensitivity_counts.items())
            ),
            "bookingRequirementCounts": self.booking_requirement_counts,
            "dataQuality": {
                "missingCoordinates": self.missing_coordinates,
                "missingOpeningHours": self.missing_opening_hours,
                "missingSourceFetchedAt": self.missing_source_fetched_at,
                "staleOperationalData": self.stale_operational_data,
                "placesUsingMockOpeningHours": self.mock_opening_hours,
                "confidenceCounts": dict(sorted(self.confidence_counts.items())),
            },
            "priceCoverage": {
                "placesWithAnyPrice": self.places_with_any_price,
                "placesWithVerifiedPrice": self.places_with_verified_price,
                "placesWithOnlyMockPrices": self.places_with_only_mock_prices,
            },
            "geographicSummary": geographic_summary,
        }


def build_region_statistics(
    places: Iterable[PlaceStatisticsRecord],
    *,
    stale_before: datetime,
) -> tuple[list[dict[str, Any]], int]:
    accumulators: dict[str, RegionAccumulator] = {}
    planner_eligible_accumulators: dict[str, RegionAccumulator] = {}
    row_count = 0

    for place in places:
        row_count += 1
        for region_key in _region_rollups(place.region_key):
            accumulator = accumulators.setdefault(region_key, RegionAccumulator(region_key))
            accumulator.add(
                place,
                stale_before,
                direct=region_key == place.region_key,
            )
            if place.status == "active":
                planner_accumulator = planner_eligible_accumulators.setdefault(
                    region_key,
                    RegionAccumulator(region_key),
                )
                planner_accumulator.add(
                    place,
                    stale_before,
                    direct=region_key == place.region_key,
                )

    regions = []
    for region_key in sorted(
        accumulators,
        key=lambda value: (value.count(","), value),
    ):
        region = accumulators[region_key].to_dict()
        eligible = planner_eligible_accumulators.get(region_key)
        region["plannerEligible"] = _planner_eligible_metrics(
            eligible.to_dict() if eligible is not None else None
        )
        regions.append(region)
    _attach_planner_signals(regions)
    return regions, row_count


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _increment(target: dict[str, int], key: str) -> None:
    target[key] = target.get(key, 0) + 1


def _region_rollups(region_key: str) -> list[str]:
    parts = [part.strip() for part in region_key.split(",") if part.strip()]
    if len(parts) < 2 or parts[0] != "vn":
        raise ValueError(f"Invalid region_key: {region_key}")
    return [",".join(parts[:depth]) for depth in range(2, len(parts) + 1)]


def _covered_time_slots(opening_hours: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for hours in opening_hours:
        if hours.get("is24Hours"):
            covered.update(TIME_SLOTS)
            continue

        open_minutes = _parse_time(hours.get("openTime"))
        close_minutes = _parse_time(hours.get("closeTime"), is_close=True)
        if open_minutes is None or close_minutes is None:
            continue

        intervals = (
            [(open_minutes, close_minutes)]
            if close_minutes > open_minutes
            else [(open_minutes, 24 * 60), (0, close_minutes)]
        )
        for slot, slot_range in TIME_SLOTS.items():
            if any(_overlaps(interval, slot_range) for interval in intervals):
                covered.add(slot)
    return covered


def _parse_time(value: Any, *, is_close: bool = False) -> int | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return None
    if hour == 24 and minute == 0:
        return 24 * 60
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    result = hour * 60 + minute
    if is_close and result == 0:
        return 24 * 60
    return result


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return max(left[0], right[0]) < min(left[1], right[1])


def _is_mock(value: dict[str, Any]) -> bool:
    return bool(value.get("provenance", {}).get("isMock", False))


def _normalized_tags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    tags: set[str] = set()
    for raw_tag in value:
        tag = _normalized_label(raw_tag)
        if not tag or not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", tag):
            continue
        normalized = TAG_ALIASES.get(tag, tag)
        if sum(character.isdigit() for character in normalized) > 2:
            continue
        tags.add(normalized)
    return tags


def _normalized_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    label = value.strip().lower().replace("-", "_").replace(" ", "_")
    return label or None


def _attach_planner_signals(regions: list[dict[str, Any]]) -> None:
    for region in regions:
        region_key = region["regionKey"]
        descendants = [
            candidate
            for candidate in regions
            if candidate["regionKey"].startswith(f"{region_key},")
        ]
        smallest_areas = [
            candidate
            for candidate in descendants
            if candidate["plannerEligible"]["directPlaceCount"] > 0
        ]
        smallest_areas.sort(
            key=lambda candidate: (
                -candidate["plannerEligible"]["placeCount"],
                candidate["regionKey"],
            )
        )
        area_profiles = [
            {
                "regionKey": child["regionKey"],
                "placeCount": child["placeCount"],
                "activePlaceCount": child["plannerEligible"]["placeCount"],
                "topTags": _top_count_keys(
                    child["plannerEligible"]["tagCounts"],
                    limit=5,
                ),
                "topPlaceTypes": _top_count_keys(
                    child["plannerEligible"]["countsByType"],
                    limit=5,
                ),
                "timeOfDayCoverage": child["plannerEligible"][
                    "timeOfDayCoverage"
                ],
                "typicalDurationByType": child["plannerEligible"][
                    "typicalDurationByType"
                ],
                "indoorOutdoorMix": child["plannerEligible"][
                    "indoorOutdoorMix"
                ],
                "dataQuality": child["plannerEligible"]["dataQuality"],
                "geographicSummary": child["plannerEligible"][
                    "geographicSummary"
                ],
            }
            for child in smallest_areas
            if child["plannerEligible"]["placeCount"] > 0
        ][:20]
        eligible = region["plannerEligible"]
        time_coverage = {
            slot: int(eligible["timeOfDayCoverage"][slot])
            for slot in TIME_SLOTS
        }
        maximum_coverage = max(time_coverage.values(), default=0)
        strong_day_parts = [
            slot
            for slot, _ in sorted(
                time_coverage.items(),
                key=lambda item: (-item[1], item[0]),
            )[:2]
            if maximum_coverage > 0
        ]
        weak_day_parts = [
            slot
            for slot, count in time_coverage.items()
            if maximum_coverage > 0 and count < maximum_coverage * 0.5
        ]
        region["areaProfiles"] = area_profiles
        region["plannerSignals"] = {
            "statisticsLevel": "smallest_available_region",
            "dominantTags": _top_count_keys(eligible["tagCounts"], limit=8),
            "strongDayParts": strong_day_parts,
            "weakDayParts": weak_day_parts,
            "candidateAreas": [
                {
                    "regionKey": area["regionKey"],
                    "placeCount": area["placeCount"],
                    "topTags": area["topTags"],
                }
                for area in area_profiles
            ],
            "activityDiversity": {
                "uniqueTagCount": len(eligible["tagCounts"]),
                "uniquePlaceTypeCount": len(eligible["countsByType"]),
            },
        }


def _planner_eligible_metrics(region: dict[str, Any] | None) -> dict[str, Any]:
    if region is None:
        empty = RegionAccumulator("unused").to_dict()
        region = empty
    return {
        "placeCount": region["placeCount"],
        "directPlaceCount": region["directPlaceCount"],
        "countsByType": region["countsByType"],
        "tagCounts": region["tagCounts"],
        "timeOfDayCoverage": region["timeOfDayCoverage"],
        "typicalDurationByType": region["typicalDurationByType"],
        "tagTimeCoverage": region["tagTimeCoverage"],
        "tagDurationProfile": region["tagDurationProfile"],
        "indoorOutdoorMix": region["indoorOutdoorMix"],
        "weatherSensitivityCounts": region["weatherSensitivityCounts"],
        "bookingRequirementCounts": region["bookingRequirementCounts"],
        "dataQuality": region["dataQuality"],
        "priceCoverage": region["priceCoverage"],
        "geographicSummary": region["geographicSummary"],
    }


def _top_count_keys(values: dict[str, int], *, limit: int) -> list[str]:
    return [
        key
        for key, _ in sorted(
            values.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]
