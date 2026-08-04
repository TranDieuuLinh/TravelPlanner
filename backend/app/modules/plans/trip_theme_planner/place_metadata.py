"""Compatibility helpers that read place metadata across schema versions.

The latest migration replaced most of ``places.metadata_json`` with
first-class columns and child tables. Several Planner and PlaceSelector tools
were originally written against the legacy JSON shape. These helpers
prefer the new schema and gracefully fall back to the legacy JSON
payload so tests and old data continue to work.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable


LEGACY_TAG_KEYS: tuple[str, ...] = (
    "tags",
    "placeTags",
    "categories",
)


PLACE_AMENITY_NAME_FIELDS: tuple[str, ...] = (
    "amenity_name",
    "amenityName",
    "name",
)


PLACE_GROUP_FALLBACK = {"accommodation", "attraction", "experience", "food_drink", "shopping", "wellness"}


def read_tags(
    place: Any,
    *,
    amenities: Iterable[Any] | None = None,
) -> list[str]:
    """Return a stable, deduplicated list of tags for ``place``.

    Order of preference:

    1. ``place.metadata_json[LEGACY_TAG_KEYS]`` – kept for legacy data
       and the existing test suite.
    2. ``place.amenities`` relationship – populated by the new schema.
    3. ``amenities`` argument – the caller may pass the child rows
       explicitly when the relationship is not eagerly loaded.
    """

    tags: list[str] = []
    seen: set[str] = set()

    metadata = getattr(place, "metadata_json", None) or {}
    for key in LEGACY_TAG_KEYS:
        values = metadata.get(key)
        if isinstance(values, list):
            for raw in values:
                if not isinstance(raw, str):
                    continue
                normalized = raw.strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                tags.append(normalized)

    amenity_source = amenities
    if amenity_source is None:
        amenity_source = getattr(place, "amenities", None)

    for amenity in amenity_source or ():
        for field in PLACE_AMENITY_NAME_FIELDS:
            value = getattr(amenity, field, None)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    tags.append(normalized)
                break

    return tags


def read_place_group(place: Any) -> str | None:
    """Resolve the legacy ``placeGroup`` marker.

    The new schema has no direct equivalent. We fall back to a small
    set of well-known buckets inferred from ``place_type`` so downstream
    semantic categories keep working. When the Google Maps import stored
    the full ``types`` list inside ``metadata.google.types``, we iterate
    through it and pick the first bucket we recognise. This is critical
    for the PlaceSelector tool because the Google ``place_type`` value is often
    a free-form category string (e.g. ``"Bún chả"``) that does not match
    the legacy whitelist.
    """

    metadata = getattr(place, "metadata_json", None) or {}
    direct = metadata.get("placeGroup") or metadata.get("place_group")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    place_type = (getattr(place, "place_type", None) or "").strip().lower()
    if place_type in PLACE_GROUP_FALLBACK:
        return place_type

    google_payload = metadata.get("google") or {}
    google_category = (
        google_payload.get("category") if isinstance(google_payload, dict) else None
    )
    if isinstance(google_category, str) and google_category.strip():
        normalized_category = google_category.strip().lower()
        if normalized_category in PLACE_GROUP_FALLBACK:
            return normalized_category
        # Fall back to the known Google primary/types catalogue when the
        # raw category string is not whitelisted.
        bucket = GOOGLE_TYPES_CATEGORY.get(normalized_category)
        if bucket is not None and bucket in PLACE_GROUP_FALLBACK:
            return bucket

    google_types = (
        google_payload.get("types") if isinstance(google_payload, dict) else None
    )
    if isinstance(google_types, list):
        for raw_type in google_types:
            if not isinstance(raw_type, str):
                continue
            bucket = GOOGLE_TYPES_CATEGORY.get(raw_type.strip().lower())
            if bucket is not None and bucket in PLACE_GROUP_FALLBACK:
                return bucket

    return None


# Mirror of the Google Maps ``types`` -> ``PLACE_GROUP_CATEGORY`` mapping
# kept in ``app.modules.plans.place_selector.place_tool``. Defined here so that
# ``read_place_group`` can resolve a bucket without importing the finder
# tool (which itself imports this module, causing a circular import).
GOOGLE_TYPES_CATEGORY: dict[str, str] = {
    "amusement_park": "entertainment",
    "aquarium": "entertainment",
    "art_gallery": "attraction",
    "bakery": "food_drink",
    "bar": "food_drink",
    "bowling_alley": "entertainment",
    "book_store": "shopping",
    "cafe": "food_drink",
    "campground": "nature",
    "casino": "entertainment",
    "cemetery": "attraction",
    "church": "attraction",
    "city_hall": "attraction",
    "clothing_store": "shopping",
    "coffee_shop": "food_drink",
    "convenience_store": "shopping",
    "courthouse": "attraction",
    "cultural_center": "attraction",
    "department_store": "shopping",
    "embassy": "attraction",
    "fire_station": "transport",
    "fountain": "attraction",
    "gym": "entertainment",
    "hindu_temple": "attraction",
    "historical_landmark": "attraction",
    "historical_place": "attraction",
    "hospital": "transport",
    "library": "attraction",
    "local_government_office": "attraction",
    "lodging": "accommodation",
    "meal_delivery": "food_drink",
    "meal_takeaway": "food_drink",
    "monument": "attraction",
    "mosque": "attraction",
    "movie_theater": "entertainment",
    "museum": "attraction",
    "natural_feature": "nature",
    "night_club": "entertainment",
    "observation_deck": "attraction",
    "park": "nature",
    "pharmacy": "shopping",
    "place_of_worship": "attraction",
    "plaza": "attraction",
    "point_of_interest": "attraction",
    "police": "transport",
    "post_office": "transport",
    "restaurant": "food_drink",
    "rv_park": "accommodation",
    "school": "attraction",
    "scenic_spot": "nature",
    "shopping_mall": "shopping",
    "spa": "entertainment",
    "square": "attraction",
    "stadium": "entertainment",
    "store": "shopping",
    "subway_station": "transport",
    "supermarket": "shopping",
    "synagogue": "attraction",
    "tourist_attraction": "attraction",
    "train_station": "transport",
    "transit_station": "transport",
    "university": "attraction",
    "zoo": "entertainment",
}


def read_rating(place: Any) -> float | None:
    """Return the place rating from the column, falling back to legacy JSON."""

    value = getattr(place, "rating", None)
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass

    metadata = getattr(place, "metadata_json", None) or {}
    for key in ("rating", "avgRating", "averageRating"):
        raw = metadata.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def read_review_count(place: Any) -> int:
    """Return the place review count from the column, falling back to legacy JSON."""

    value = getattr(place, "review_count", None)
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    metadata = getattr(place, "metadata_json", None) or {}
    for key in ("reviewCount", "review_count", "reviewcount"):
        raw = metadata.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def read_price_level(place: Any) -> str | None:
    """Return a normalized price tier if either schema exposes one."""

    metadata = getattr(place, "metadata_json", None) or {}
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


def read_description(place: Any) -> str | None:
    """Return a human description for the place."""

    metadata = getattr(place, "metadata_json", None) or {}
    for key in ("description", "summary", "blurb"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    google_payload = metadata.get("google") if isinstance(metadata, dict) else None
    if isinstance(google_payload, dict):
        value = google_payload.get("description")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_daily_cost(place: Any) -> int | None:
    """Estimate a per-day cost for the place.

    The legacy ``metadata.prices`` array is no longer populated. The new
    schema stores prices via the Google payload and we approximate a
    daily cost using the ``priceLevel`` hint plus the currency-free
    marker in ``metadata.finance.dailyBudget``.
    """

    metadata = getattr(place, "metadata_json", None) or {}
    finance = metadata.get("finance") if isinstance(metadata, dict) else None
    if isinstance(finance, dict):
        raw = finance.get("dailyBudget") or finance.get("estimatedCost")
        if raw is not None:
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                pass

    price_level = read_price_level(place)
    if price_level is not None:
        return _price_level_to_cost(price_level)

    google_payload = metadata.get("google") if isinstance(metadata, dict) else None
    if isinstance(google_payload, dict):
        google_level = google_payload.get("priceLevel") or google_payload.get("price_level")
        if isinstance(google_level, str) and google_level.strip():
            return _price_level_to_cost(google_level.strip())

    return None


def _price_level_to_cost(value: str) -> int | None:
    normalized = value.strip().lower()
    table = {
        "free": 0,
        "$": 100_000,
        "low": 100_000,
        "budget": 100_000,
        "cheap": 100_000,
        "$$": 300_000,
        "medium": 300_000,
        "moderate": 300_000,
        "mid_range": 300_000,
        "$$$": 700_000,
        "high": 700_000,
        "expensive": 700_000,
        "premium": 700_000,
        "$$$$": 1_500_000,
        "luxury": 1_500_000,
    }
    return table.get(normalized)


def rating_or_default(value: Decimal | float | int | None, *, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
