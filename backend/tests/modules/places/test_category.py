from app.modules.places.category import canonical_place_category


def test_normalizes_verified_provider_categories() -> None:
    assert canonical_place_category("Museum") == "culture"
    assert canonical_place_category("Bảo tàng") == "culture"
    assert canonical_place_category("Restaurant") == "food"
    assert canonical_place_category("Coffee shop") == "cafe"


def test_unknown_or_missing_provider_category_does_not_use_ai_fallback() -> None:
    assert canonical_place_category(None) == "other"
    assert canonical_place_category("Unrecognized venue type") == "other"
