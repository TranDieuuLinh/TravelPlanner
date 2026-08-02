from __future__ import annotations

import pytest

from scripts.import_google_places_to_postgres import _build_place_row


def _place_csv_row(description: str) -> dict[str, str]:
    return {
        "place_id": "google-place-1",
        "title": "Example Place",
        "category": "Tourist attraction",
        "description": description,
        "latitude": "21.0285",
        "longitude": "105.8542",
        "city": "Ha Noi",
    }


@pytest.mark.parametrize(
    "missing_value",
    ["", "   ", "nan", "NaN", "null", "NONE", "N/A", "<NA>"],
)
def test_place_import_normalizes_missing_description_markers(
    missing_value: str,
) -> None:
    record = _build_place_row(_place_csv_row(missing_value))

    assert record is not None
    assert record["metadata"]["google"]["description"] is None


def test_place_import_preserves_real_description() -> None:
    record = _build_place_row(
        _place_csv_row("  Historic lakeside temple with a public courtyard.  ")
    )

    assert record is not None
    assert (
        record["metadata"]["google"]["description"]
        == "Historic lakeside temple with a public courtyard."
    )
