from __future__ import annotations

import re
import unicodedata


_CATEGORY_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "food",
        (
            "restaurant",
            "fast food",
            "food court",
            "meal takeaway",
            "bakery",
            "barbecue",
            "bistro",
            "cafeteria",
            "deli",
            "grill",
            "hawker stall",
            "ice cream shop",
            "noodle shop",
            "soup kitchen",
            "steak house",
            "tiffin center",
            "nha hang",
            "quan an",
            "quan nhau",
            "tiem banh",
        ),
    ),
    (
        "cafe",
        (
            "cafe",
            "coffee",
            "coffee shop",
            "bubble tea",
            "tea house",
            "quan cafe",
            "quan coffee",
        ),
    ),
    (
        "culture",
        (
            "museum",
            "art gallery",
            "cultural center",
            "historical landmark",
            "historical place",
            "heritage",
            "monument",
            "memorial",
            "temple",
            "pagoda",
            "church",
            "cathedral",
            "mosque",
            "synagogue",
            "place of worship",
            "art center",
            "art studio",
            "community center",
            "congregation",
            "exhibition and trade center",
            "movie theater",
            "performing arts theater",
            "religious destination",
            "shrine",
            "spiritist center",
            "village hall",
            "bao tang",
            "di tich",
            "den chua",
        ),
    ),
    (
        "hotel",
        (
            "hotel",
            "lodging",
            "hostel",
            "motel",
            "guest house",
            "resort",
            "homestay",
            "accommodation",
            "holiday apartment rental",
            "serviced accommodation",
            "vacation rental",
        ),
    ),
    (
        "transport",
        (
            "airport",
            "bus station",
            "train station",
            "transit station",
            "subway station",
            "ferry terminal",
            "station",
            "transport",
            "bus stop",
            "parking lot",
        ),
    ),
    (
        "shopping",
        (
            "shopping mall",
            "department store",
            "marketplace",
            "market",
            "store",
            "shop",
            "supermarket",
            "florist",
            "handicraft",
            "outlet mall",
        ),
    ),
    (
        "nature",
        (
            "national park",
            "nature reserve",
            "natural feature",
            "park",
            "garden",
            "waterfall",
            "lake",
            "cave",
            "mountain",
            "forest",
        ),
    ),
    ("beach", ("beach", "coast", "island")),
    (
        "nightlife",
        (
            "night club",
            "nightclub",
            "nightlife",
            "bar",
            "pub",
            "beer hall",
            "brewpub",
            "karaoke",
            "live music venue",
            "video karaoke",
        ),
    ),
    (
        "wellness",
        (
            "spa",
            "wellness",
            "massage",
            "yoga",
            "beauty salon",
            "fitness center",
            "gym",
            "physical therapist",
            "pilates studio",
        ),
    ),
    (
        "adventure",
        (
            "adventure",
            "hiking",
            "trekking",
            "kayak",
            "athletic club",
            "boxing gym",
            "campground",
            "golf course",
            "golf driving range",
            "gymnastics center",
            "indoor golf course",
            "indoor swimming pool",
            "pickleball court",
            "soccer field",
            "sports club",
            "sports complex",
            "stadium",
            "swimming pool",
            "tennis court",
        ),
    ),
    (
        "family",
        (
            "zoo",
            "aquarium",
            "amusement park",
            "family",
            "children s amusement center",
            "playground",
            "recreation center",
            "video arcade",
        ),
    ),
    ("cemetery", ("cemetery",)),
    (
        "attraction",
        (
            "tourist attraction",
            "attraction",
            "observation deck",
            "scenic spot",
            "point of interest",
            "plaza",
            "square",
            "bridge",
        ),
    ),
)


def canonical_place_category(place_type: str | None) -> str:
    """Map a verified database/provider place type to the API taxonomy.

    The input must come from the internal Places catalog or an external place
    resolver. Candidate categories inferred from prompts, captions, STT, or OCR
    must not be passed here as a fallback.
    """

    normalized = _normalize(place_type or "")
    if not normalized:
        return "other"
    padded = f" {normalized} "
    for category, markers in _CATEGORY_MARKERS:
        if any(f" {marker} " in padded for marker in markers):
            return category
    return "other"


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()
