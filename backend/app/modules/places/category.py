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
    ("nightlife", ("night club", "nightclub", "nightlife", "bar", "pub")),
    ("wellness", ("spa", "wellness", "massage", "yoga")),
    ("adventure", ("adventure", "hiking", "trekking", "kayak")),
    ("family", ("zoo", "aquarium", "amusement park", "family")),
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
