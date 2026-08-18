from __future__ import annotations

from app.shared.tools.search_places.normalization import normalize_text


_RESTAURANT = frozenset({"restaurant", "food", "food venue"})
_DRINK_DESSERT = frozenset(
    {
        "drink dessert",
        "drink_dessert",
        "drinkdessert",
        "cafe",
        "ca phe",
        "coffee",
        "coffee shop",
        "tea house",
        "bubble tea",
        "bakery",
        "dessert",
        "patisserie",
    }
)
_ENTERTAINMENT = frozenset(
    {"entertainment", "game center", "cinema", "karaoke", "music venue"}
)
_ENTERTAINMENT_NAME_MARKERS = (
    "bi a",
    "billiard",
    "billiards",
    "bowling",
    "candles",
    "culcat",
    "cua hang",
    "dau vai",
    "elly",
    "entertainment",
    "faculty",
    "game center",
    "garden center",
    "garmin",
    "giai co",
    "gift shop",
    "gifts",
    "golf",
    "interior plant service",
    "karaoke",
    "khoa",
    "kinh mat",
    "mall",
    "massage",
    "miniwood design",
    "mood on",
    "music box",
    "music academy",
    "music school",
    "music talent",
    "musicbox",
    "noraebang",
    "pilates",
    "pickleball",
    "school",
    "photo booth",
    "showroom",
    "spa",
    "studio",
    "souvenir",
    "souvenirs",
    "souvernirs",
    "store",
    "art supply store",
    "artistic handicrafts",
    "tam quat",
    "tiredcity",
    "tri lieu",
    "truong dh",
    "trung tam am nhac",
    "vong hoa",
    "nha tang le",
    "cong ty",
    "costume rental service",
    "vinhomes",
)
_DRINK_NAME_MARKERS = (
    "cafe",
    "ca phe",
    "coffee",
    "tea",
    "tra sua",
)
_RESTAURANT_NAME_MARKERS = (
    "bun cha",
    "com",
    "lau",
    "mi van than",
    "pho",
    "quan mi",
    "sui cao",
)
_PUBLIC_PLACE_NAME_MARKERS = (
    "pho di bo",
    "walking street",
)


def planner_category(value: str | None) -> str:
    """Map source categories to the Planner's canonical node type."""
    normalized = normalize_text(value)
    if normalized in _RESTAURANT:
        return "restaurant"
    if normalized in _DRINK_DESSERT:
        return "drink_dessert"
    if normalized in _ENTERTAINMENT:
        return "entertainment"
    if normalized == "accommodation":
        return "accommodation"
    return "travel_place"


def planner_category_for_candidate(
    value: str | None,
    *,
    name: str | None,
    tags: list[str] | tuple[str, ...] = (),
    pool_category: str | None = None,
    context: str | None = None,
) -> str:
    """Correct obvious leisure venues mislabeled as TravelPlace upstream."""
    category = planner_category(value)
    padded_name = f" {normalize_text(name)} "
    if category == "restaurant" and any(
        f" {marker} " in padded_name for marker in _PUBLIC_PLACE_NAME_MARKERS
    ):
        return "travel_place"
    identity = normalize_text(" ".join([name or "", context or "", *tags]))
    padded_identity = f" {identity} "
    has_drink_tag = any(planner_category(tag) == "drink_dessert" for tag in tags)
    if category != "accommodation" and (
        any(f" {marker} " in padded_name for marker in _DRINK_NAME_MARKERS)
        or any(
            f" {marker} " in padded_identity for marker in _DRINK_NAME_MARKERS
        )
        or planner_category(pool_category) == "drink_dessert"
        or has_drink_tag
    ):
        return "drink_dessert"
    if category != "accommodation" and any(
        f" {marker} " in padded_name
        for marker in _RESTAURANT_NAME_MARKERS
    ):
        return "restaurant"
    if category != "travel_place":
        return category
    if normalize_text(pool_category) == "shopping":
        return "entertainment"
    if any(
        f" {marker} " in padded_identity
        for marker in _ENTERTAINMENT_NAME_MARKERS
    ):
        return "entertainment"
    if "entertainment" in {normalize_text(tag) for tag in tags}:
        return "entertainment"
    return category
