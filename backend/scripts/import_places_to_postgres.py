from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.modules.places.model import Place


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import schema-13 Place data into PostgreSQL."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_DIR / "database" / "places.csv",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be at least 1")

    imported_rows = 0
    with SessionLocal() as session:
        if session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("This importer requires PostgreSQL")

        for batch in _batches(_read_places(args.source), args.batch_size):
            statement = postgresql_insert(Place.__table__).values(batch)
            excluded = statement.excluded
            update_values = {
                column.name: excluded[column.name]
                for column in Place.__table__.columns
                if column.name not in {"id", "created_at", "revision", "updated_at"}
            }
            update_values["revision"] = Place.__table__.c.revision + 1
            update_values["updated_at"] = func.now()
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Place.__table__.c.id],
                    set_=update_values,
                )
            )
            imported_rows += len(batch)
        session.commit()

    print(
        json.dumps(
            {
                "status": "imported",
                "importedRows": imported_rows,
                "statisticsStatus": "deferred_until_planner_request",
            },
            ensure_ascii=False,
        )
    )
    return 0


def _read_places(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            try:
                yield {
                    "id": row["id"],
                    "name": row["name"],
                    "place_type": row["place_type"],
                    "address": row["address"] or None,
                    "city": row["city"] or None,
                    "country": row["country"] or None,
                    "country_code": row["country_code"] or None,
                    "region_key": row["region_key"],
                    "primary_area": row["primary_area"] or None,
                    "latitude": Decimal(row["latitude"]) if row["latitude"] else None,
                    "longitude": Decimal(row["longitude"]) if row["longitude"] else None,
                    "status": row["status"],
                    "opening_hours": json.loads(row["opening_hours"] or "[]"),
                    "typical_duration_minutes": (
                        int(row["typical_duration_minutes"])
                        if row["typical_duration_minutes"]
                        else None
                    ),
                    "data_confidence": row["data_confidence"],
                    "source_fetched_at": _datetime(row["source_fetched_at"]),
                    "revision": int(row["revision"]),
                    "metadata": json.loads(row["metadata"] or "{}"),
                    "deleted_at": _datetime(row["deleted_at"]),
                    "created_at": _datetime(row["created_at"]),
                    "updated_at": _datetime(row["updated_at"]),
                }
            except (KeyError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid Place at CSV line {line_number}: {error}") from error


def _datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _batches(
    rows: Iterator[dict[str, Any]],
    batch_size: int,
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


if __name__ == "__main__":
    raise SystemExit(main())
