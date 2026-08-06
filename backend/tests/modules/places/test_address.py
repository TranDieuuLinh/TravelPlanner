from app.modules.places.address import (
    address_numbers,
    address_tokens,
    normalize_address,
)


def test_normalizes_vietnamese_and_english_address_forms() -> None:
    left = "58 P. Quốc Tử Giám, Hà Nội 100000"
    right = "No. 58 Quoc Tu Giam Street, Hanoi"

    assert address_numbers(left) == address_numbers(right) == {"58"}
    assert {"quoc", "giam"}.issubset(address_tokens(left))
    assert address_tokens(left) == address_tokens(right)


def test_ignores_plus_codes_and_postal_codes() -> None:
    assert address_numbers("2VH2+4WJ, Hà Nội 100000") == set()
    assert "100000" not in normalize_address("Hà Nội 100000")


def test_normalizes_hyphenated_house_number_suffix() -> None:
    assert address_numbers("58-A Quốc Tử Giám") == {"58a"}
    assert address_numbers("58A Quoc Tu Giam") == {"58a"}
