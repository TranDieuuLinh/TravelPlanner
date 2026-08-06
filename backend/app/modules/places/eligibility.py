"""Shared eligibility guards for place search and Planner catalogs."""

from __future__ import annotations

import math
from typing import Any, Protocol


INVALID_PLACE_TYPES = {
    "",
    "nan",
    "none",
    "null",
    "unknown",
    "unspecified",
}


class SearchablePlaceRecord(Protocol):
    name: str
    place_type: str
    latitude: Any
    longitude: Any
    status: str


def valid_place_coordinates(latitude: Any, longitude: Any) -> bool:
    try:
        latitude_value = float(latitude)
        longitude_value = float(longitude)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(latitude_value) or not math.isfinite(longitude_value):
        return False
    if not -90 <= latitude_value <= 90:
        return False
    if not -180 <= longitude_value <= 180:
        return False
    return not (latitude_value == 0.0 and longitude_value == 0.0)


def valid_place_type(value: str | None) -> bool:
    return " ".join((value or "").split()).casefold() not in INVALID_PLACE_TYPES


def valid_canonical_place_name(value: str | None) -> bool:
    cleaned = " ".join((value or "").split())
    return bool(cleaned and any(character.isalnum() for character in cleaned))


def place_record_is_search_eligible(record: SearchablePlaceRecord) -> bool:
    return bool(
        getattr(record, "status", "active") == "active"
        and valid_canonical_place_name(record.name)
        and valid_place_type(record.place_type)
        and valid_place_coordinates(record.latitude, record.longitude)
    )
