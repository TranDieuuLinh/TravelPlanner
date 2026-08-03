from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scripts.import_google_places_to_postgres import (
    _build_image_row,
    _import_child_rows,
)
from app.modules.places.model import PlaceImage


def test_image_import_skips_rows_for_places_missing_from_catalog(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "images.csv"
    csv_path.write_text(
        "place_id,image_title,image_url\n"
        "known,All,https://images.example/known.jpg\n"
        "missing,All,https://images.example/missing.jpg\n",
        encoding="utf-8",
    )
    session = MagicMock()
    session.scalars.return_value = ["known"]

    inserted, skipped, distinct = _import_child_rows(
        session,
        csv_path,
        builder=_build_image_row,
        limit=None,
        dry_run=True,
        table=PlaceImage,
    )

    assert inserted == 1
    assert skipped == 1
    assert distinct == 1
