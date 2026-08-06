import pytest

from app.modules.places.category import canonical_place_category


def test_normalizes_verified_provider_categories() -> None:
    assert canonical_place_category("Museum") == "culture"
    assert canonical_place_category("Bảo tàng") == "culture"
    assert canonical_place_category("Restaurant") == "food"
    assert canonical_place_category("Coffee shop") == "cafe"


def test_unknown_or_missing_provider_category_does_not_use_ai_fallback() -> None:
    assert canonical_place_category(None) == "other"
    assert canonical_place_category("Unrecognized venue type") == "other"


@pytest.mark.parametrize(
    ("place_type", "category"),
    [
        ("Bistro", "food"),
        ("Tea house", "cafe"),
        ("Shrine", "culture"),
        ("Holiday apartment rental", "hotel"),
        ("Bus stop", "transport"),
        ("Outlet mall", "shopping"),
        ("Brewpub", "nightlife"),
        ("Video karaoke", "nightlife"),
        ("Pilates studio", "wellness"),
        ("Pickleball court", "adventure"),
        ("Indoor golf course", "adventure"),
        ("Children's amusement center", "family"),
    ],
)
def test_maps_clear_tourism_relevant_provider_categories(
    place_type: str,
    category: str,
) -> None:
    assert canonical_place_category(place_type) == category


@pytest.mark.parametrize(
    "place_type",
    ["Apartment building", "Building", "Farm", "Manufacturer", "Preschool"],
)
def test_keeps_broad_or_non_tourism_types_as_other(place_type: str) -> None:
    assert canonical_place_category(place_type) == "other"
