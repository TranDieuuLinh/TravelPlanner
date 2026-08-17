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
