from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.places.eligibility import (
    place_record_is_search_eligible,
    valid_canonical_place_name,
    valid_place_coordinates,
    valid_place_type,
)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (None, 105.8),
        (21.0, None),
        (0, 0),
        (91, 105.8),
        (-91, 105.8),
        (21.0, 181),
        (21.0, -181),
        (float("nan"), 105.8),
        (21.0, float("inf")),
    ],
)
def test_invalid_coordinates_are_rejected(latitude: object, longitude: object) -> None:
    assert valid_place_coordinates(latitude, longitude) is False


def test_valid_coordinates_accept_decimal_values_and_zero_on_one_axis() -> None:
    assert valid_place_coordinates(Decimal("21.0"), Decimal("105.8")) is True
    assert valid_place_coordinates(0, 105.8) is True


@pytest.mark.parametrize("value", [None, "", "nan", "NULL", "unknown", " unspecified "])
def test_placeholder_place_types_are_rejected(value: str | None) -> None:
    assert valid_place_type(value) is False


def test_name_guard_keeps_non_latin_names_but_rejects_symbols() -> None:
    assert valid_canonical_place_name("福恩寺") is True
    assert valid_canonical_place_name("비타민노래방") is True
    assert valid_canonical_place_name("*****") is False
    assert valid_canonical_place_name(" . ") is False


@pytest.mark.parametrize("status", ["merged", "quarantined", "draft"])
def test_non_active_catalog_status_is_rejected(status: str) -> None:
    record = SimpleNamespace(
        name="Hồ Tây",
        place_type="Lake",
        latitude=21.05,
        longitude=105.82,
        status=status,
    )
    assert place_record_is_search_eligible(record) is False
