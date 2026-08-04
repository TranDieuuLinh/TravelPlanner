from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scripts.import_google_places_to_postgres import (
    _build_image_row,
    _import_child_rows,
    _refresh_places_opening_hours,
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


def test_opening_hours_refresh_commits_in_bounded_batches() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        ("place-1", "Monday", "09:00-17:00"),
        ("place-2", "Tuesday", "10:00-18:00"),
        ("place-3", "Wednesday", "11:00-19:00"),
    ]
    places = {
        place_id: MagicMock(revision=1)
        for place_id in ("place-1", "place-2", "place-3")
    }
    session.get.side_effect = lambda _model, place_id: places[place_id]

    _refresh_places_opening_hours(session, batch_size=2)

    assert session.commit.call_count == 2
    session.expunge_all.assert_called_once_with()
    assert places["place-1"].opening_hours[0]["dayName"] == "Monday"
    assert places["place-3"].revision == 2
