"""Import the csv_relational/ Google Maps dataset into PostgreSQL.

This script reads the five relational CSV files produced by the
``auto-crawl/read_parquet`` pipeline and upserts them into the new
schema introduced by migration ``20260731_0002``:

* ``places.csv``              -> ``places``
* ``amenities.csv``           -> ``place_amenities``
* ``operating_hours.csv``     -> ``place_opening_hours``
* ``images.csv``              -> ``place_images``
* ``reviews.csv``             -> ``reviews`` (Google Maps place reviews)

The script is idempotent: every child table has a uniqueness constraint
so ``INSERT ... ON CONFLICT DO NOTHING`` is safe to re-run.

Two safe-by-default flags are exposed:

* ``--dry-run`` does not write anything but prints a summary of what
  would be inserted or skipped.
* ``--limit N`` truncates the import to the first ``N`` rows per table
  for smoke testing.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.places.model import (  # noqa: E402
    Place,
    PlaceAmenity,
    PlaceImage,
    PlaceOpeningHour,
    PlaceReview,
)


ADMIN_PREFIXES = (
    "thanh-pho-",
    "thi-tran-",
    "thi-xa-",
    "tinh-",
    "quan-",
    "huyen-",
    "phuong-",
    "xa-",
)

DAY_NAME_TO_NUMBER = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import csv_relational/ Google Maps data into PostgreSQL."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PROJECT_DIR / "auto-crawl" / "csv_relational",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional per-table row limit for smoke testing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and summarise but do not write to the database.",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of tables to import (places,amenities,operating_hours,images,reviews).",
    )
    return parser.parse_args()


def _read_csv(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield {key: (value or "") for key, value in row.items()}


def _iter_limited(rows: Iterable[dict[str, Any]], limit: int | None) -> Iterator[dict[str, Any]]:
    if limit is None:
        yield from rows
        return
    for index, row in enumerate(rows):
        if index >= limit:
            return
        yield row


def _slugify_region_part(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD", value.strip().replace("Đ", "D").replace("đ", "d")
    )
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    for prefix in ADMIN_PREFIXES:
        if slug.startswith(prefix):
            return slug[len(prefix) :]
    return slug


def _build_region_key(city: str, primary_area: str) -> str:
    parts = ["vn"]
    for raw in (city, primary_area):
        slug = _slugify_region_part(raw)
        if slug and slug not in parts:
            parts.append(slug)
    return ",".join(parts) if len(parts) >= 2 else "vn,unmapped"


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _normalise_day(value: str) -> str:
    return (value or "").strip().lower()


def _opening_hours_payload(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        day = _normalise_day(row.get("day_of_week"))
        if not day:
            continue
        slots = (row.get("time_slots") or "").strip() or None
        payload.append(
            {
                "dayOfWeek": DAY_NAME_TO_NUMBER.get(day),
                "dayName": row["day_of_week"].strip(),
                "rawTimeSlots": slots,
                "is24Hours": False,
            }
        )
    return payload


# ---------------------------------------------------------------------------
# row builders
# ---------------------------------------------------------------------------


def _build_place_row(row: dict[str, str]) -> dict[str, Any] | None:
    place_id = row.get("place_id", "").strip()
    name = row.get("title", "").strip()
    if not place_id or not name:
        return None

    city = (row.get("city") or "").strip() or None
    borough = (row.get("borough") or "").strip() or None
    latitude = _parse_decimal(row.get("latitude"))
    longitude = _parse_decimal(row.get("longitude"))

    if latitude is None or longitude is None:
        # Without coordinates the place cannot be planned, so skip it.
        return None

    primary_area = borough or city
    region_key = _build_region_key(city or "", primary_area or "")

    rating = _parse_decimal(row.get("rating"))
    if rating is not None and (rating < 0 or rating > 5):
        rating = None

    review_count = _parse_int(row.get("review_count")) or 0

    metadata: dict[str, Any] = {
        "google": {
            "plusCode": row.get("plus_code") or None,
            "state": row.get("state") or None,
            "borough": borough,
            "category": row.get("category") or None,
            "description": row.get("description") or None,
        },
    }

    return {
        "id": place_id,
        "name": name,
        "place_type": (row.get("category") or "unknown").strip()[:96] or "unknown",
        "address": (row.get("address") or None),
        "city": city,
        "country": (row.get("country") or "Việt Nam"),
        "country_code": (row.get("country") or "VN")[:8] or "VN",
        "region_key": region_key,
        "primary_area": primary_area,
        "latitude": latitude,
        "longitude": longitude,
        "status": "active",
        "opening_hours": [],
        "data_confidence": "medium",
        "source_platform": (row.get("source_platform") or "google_maps")[:64] or "google_maps",
        "source_link": row.get("source_link") or None,
        "plus_code": (row.get("plus_code") or None),
        "rating": rating,
        "review_count": review_count,
        "source_fetched_at": _parse_datetime(row.get("source_fetched_at")) or datetime.now(timezone.utc),
        "revision": 1,
        # Core inserts use SQLAlchemy table column keys, so this must match
        # the physical column name rather than the ORM attribute name.
        "metadata": metadata,
    }


def _build_opening_hour_row(place_id: str, row: dict[str, str]) -> dict[str, Any] | None:
    day = (row.get("day_of_week") or "").strip()
    slots = (row.get("time_slots") or "").strip()
    if not day or not slots:
        return None
    return {
        "place_id": place_id,
        "day_of_week": day[:16],
        "time_slots": slots,
    }


def _build_image_row(place_id: str, row: dict[str, str]) -> dict[str, Any] | None:
    url = (row.get("image_url") or "").strip()
    if not url:
        return None
    return {
        "place_id": place_id,
        "image_title": (row.get("image_title") or None),
        "image_url": url,
    }


def _build_amenity_row(place_id: str, row: dict[str, str]) -> dict[str, Any] | None:
    name = (row.get("amenity_name") or "").strip()
    if not name:
        return None
    return {
        "place_id": place_id,
        "category_group": (row.get("category_group") or "General").strip()[:64] or "General",
        "amenity_name": name[:255],
    }


def _build_review_row(place_id: str, row: dict[str, str]) -> dict[str, Any] | None:
    review_id = (row.get("review_id") or "").strip()
    text_value = (row.get("review_text") or "").strip()
    if not review_id:
        return None
    rating = _parse_int(row.get("rating"))
    if rating is not None and not 1 <= rating <= 5:
        rating = None
    return {
        "id": review_id[:96],
        "place_id": place_id,
        "author_name": (row.get("author_name") or None),
        "rating": rating,
        "published_at": _parse_datetime(row.get("published_at")),
        "when_text": (row.get("when_text") or None),
        "language": (row.get("language") or None),
        "review_text": text_value or None,
    }


# ---------------------------------------------------------------------------
# import pipeline
# ---------------------------------------------------------------------------


def _bulk_insert(
    session: Session,
    rows: list[dict[str, Any]],
    table: Any,
    *,
    page_size: int = 5000,
) -> int:
    if not rows:
        return 0
    column_count = max(len(row) for row in rows)
    effective_page_size = min(
        page_size,
        max(1, 60_000 // column_count),
    )
    total = 0
    for start in range(0, len(rows), effective_page_size):
        chunk = rows[start : start + effective_page_size]
        # Omitting a conflict target makes PostgreSQL ignore conflicts from
        # either the primary key or any unique constraint on child tables.
        statement = (
            postgresql_insert(table.__table__)
            .values(chunk)
            .on_conflict_do_nothing()
            .returning(*table.__table__.primary_key.columns)
        )
        result = session.execute(statement)
        total += len(result.fetchall())
    return total


def _import_places(
    session: Session,
    csv_path: Path,
    *,
    limit: int | None,
    dry_run: bool,
) -> tuple[int, int]:
    skipped = 0
    rows: list[dict[str, Any]] = []
    for raw in _iter_limited(_read_csv(csv_path), limit):
        record = _build_place_row(raw)
        if record is None:
            skipped += 1
            continue
        rows.append(record)
    if dry_run:
        return len(rows), skipped
    inserted = _bulk_insert(session, rows, Place)
    session.commit()
    return inserted, skipped


def _import_child_rows(
    session: Session,
    csv_path: Path,
    *,
    builder,
    limit: int | None,
    dry_run: bool,
    table: Any,
    key: str = "place_id",
) -> tuple[int, int, int]:
    inserted = 0
    skipped = 0
    distinct_place_ids = 0
    seen_place_ids: set[str] = set()
    existing_place_ids = set(session.scalars(select(Place.id)))
    rows: list[dict[str, Any]] = []
    for raw in _iter_limited(_read_csv(csv_path), limit):
        place_id = (raw.get("place_id") or "").strip()
        if not place_id or place_id not in existing_place_ids:
            skipped += 1
            continue
        seen_place_ids.add(place_id)
        record = builder(place_id, raw)
        if record is None:
            skipped += 1
            continue
        rows.append(record)
        if len(rows) >= 10000:
            if not dry_run:
                inserted += _bulk_insert(session, rows, table)
                session.commit()
            else:
                inserted += len(rows)
            rows = []
    if rows:
        if not dry_run:
            inserted += _bulk_insert(session, rows, table)
            session.commit()
        else:
            inserted += len(rows)
    distinct_place_ids = len(seen_place_ids)
    return inserted, skipped, distinct_place_ids


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()

    source_dir: Path = args.source_dir
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")

    only = (
        {item.strip() for item in args.only.split(",") if item.strip()}
        if args.only
        else None
    )

    summary: dict[str, Any] = {
        "dryRun": args.dry_run,
        "sourceDir": str(source_dir),
        "limit": args.limit,
        "tables": {},
    }

    with SessionLocal() as session:
        # --- places ---
        if only is None or "places" in only:
            csv_path = source_dir / "places.csv"
            if not csv_path.exists():
                raise SystemExit(f"Missing CSV: {csv_path}")
            inserted, skipped = _import_places(
                session, csv_path, limit=args.limit, dry_run=args.dry_run
            )
            summary["tables"]["places"] = {
                "inserted": inserted,
                "skipped": skipped,
            }

        # --- operating_hours (used to populate places.opening_hours) ---
        if only is None or "operating_hours" in only:
            csv_path = source_dir / "operating_hours.csv"
            if csv_path.exists():
                inserted, skipped, distinct = _import_child_rows(
                    session,
                    csv_path,
                    builder=_build_opening_hour_row,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    table=PlaceOpeningHour,
                )
                summary["tables"]["place_opening_hours"] = {
                    "inserted": inserted,
                    "skipped": skipped,
                    "distinctPlaceIds": distinct,
                }
                if not args.dry_run:
                    _refresh_places_opening_hours(session)

        # --- amenities ---
        if only is None or "amenities" in only:
            csv_path = source_dir / "amenities.csv"
            if csv_path.exists():
                inserted, skipped, distinct = _import_child_rows(
                    session,
                    csv_path,
                    builder=_build_amenity_row,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    table=PlaceAmenity,
                )
                summary["tables"]["place_amenities"] = {
                    "inserted": inserted,
                    "skipped": skipped,
                    "distinctPlaceIds": distinct,
                }

        # --- images ---
        if only is None or "images" in only:
            csv_path = source_dir / "images.csv"
            if csv_path.exists():
                inserted, skipped, distinct = _import_child_rows(
                    session,
                    csv_path,
                    builder=_build_image_row,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    table=PlaceImage,
                )
                summary["tables"]["place_images"] = {
                    "inserted": inserted,
                    "skipped": skipped,
                    "distinctPlaceIds": distinct,
                }

        # --- reviews ---
        if only is None or "reviews" in only:
            csv_path = source_dir / "reviews.csv"
            if csv_path.exists():
                inserted, skipped, distinct = _import_child_rows(
                    session,
                    csv_path,
                    builder=_build_review_row,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    table=PlaceReview,
                )
                summary["tables"]["reviews"] = {
                    "inserted": inserted,
                    "skipped": skipped,
                    "distinctPlaceIds": distinct,
                }

        if not args.dry_run:
            session.execute(text("ANALYZE places"))
            session.execute(text("ANALYZE place_opening_hours"))
            session.execute(text("ANALYZE place_amenities"))
            session.execute(text("ANALYZE place_images"))
            session.execute(text("ANALYZE reviews"))
            session.commit()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _refresh_places_opening_hours(
    session: Session,
    *,
    batch_size: int = 500,
) -> None:
    """Aggregate child opening hours into places.opening_hours JSON.

    The CSV row shape stores one record per ``(place_id, day_of_week)``,
    which mirrors the relational table. The contract used by the planner
    is a JSON array on ``places.opening_hours`` so we rebuild that field
    from the freshly imported child rows.
    """

    place_id_column = PlaceOpeningHour.place_id
    day_column = PlaceOpeningHour.day_of_week
    slots_column = PlaceOpeningHour.time_slots

    rows = session.execute(
        select(
            place_id_column,
            day_column,
            slots_column,
        ).order_by(place_id_column, day_column)
    ).all()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for place_id, day, slots in rows:
        grouped.setdefault(place_id, []).append(
            {
                "dayOfWeek": DAY_NAME_TO_NUMBER.get(day.lower()),
                "dayName": day,
                "rawTimeSlots": slots,
                "is24Hours": False,
            }
        )

    if not grouped:
        return

    processed = 0
    for place_id, payload in grouped.items():
        place = session.get(Place, place_id)
        if place is None:
            continue
        place.opening_hours = payload
        place.revision = (place.revision or 1) + 1
        processed += 1
        if processed % batch_size == 0:
            # A single flush for tens of thousands of ORM updates can exhaust
            # the local PostgreSQL/container connection. Commit bounded batches
            # and release the identity map before continuing.
            session.commit()
            session.expunge_all()
    session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
