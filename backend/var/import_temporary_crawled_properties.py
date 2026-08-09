"""Temporarily import crawled price/menu properties into the Docker KG.

The import is intentionally reversible: every written row receives the same
batch marker in ``knowledge_properties.note``. Run with ``--delete`` to remove
only properties written by this batch.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.db.session import SessionLocal
from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty


BATCH_MARKER = "temporary_csv_import:2026-08-09"
RESTAURANT_SOURCE = "crawl-for-res-dri-des/data_crawled.csv"
ACCOMMODATION_SOURCE = "crawl-for-acommodation/data_crawled.csv"
WRITE_BATCH_SIZE = 500


def _clean_row(row: dict[str, str]) -> dict[str, str]:
    return {(key or "").lstrip("\ufeff"): (value or "").strip() for key, value in row.items()}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_clean_row(row) for row in csv.DictReader(handle)]


def _menu_images(raw: str) -> str | None:
    if not raw:
        return None
    urls = [part.strip() for part in raw.replace("&https://", "\nhttps://").splitlines() if part.strip()]
    return json.dumps(urls, ensure_ascii=False, separators=(",", ":")) if urls else None


def _sources(raw: str) -> str | None:
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed:
        return None
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def _candidate_rows(
    restaurant_path: Path,
    accommodation_path: Path,
) -> tuple[list[dict[str, str]], dict[str, str], Counter[str]]:
    properties: list[dict[str, str]] = []
    expected_types: dict[str, str] = {}
    stats: Counter[str] = Counter()

    for row in _read_csv(restaurant_path):
        entity_id = row.get("id", "")
        entity_type = row.get("type", "")
        if not entity_id or entity_type not in {"Restaurant", "DrinkDessert"}:
            stats["restaurant_invalid_rows"] += 1
            continue
        expected_types[entity_id] = entity_type
        source = row.get("source_url") or RESTAURANT_SOURCE
        price = row.get("price", "")
        if price and price != "-1":
            properties.append({"entity_id": entity_id, "key": "price", "value": price, "source": source})
            stats["price_candidates"] += 1
        menu_images = _menu_images(row.get("menu_images", ""))
        if menu_images:
            properties.append({"entity_id": entity_id, "key": "menu_images", "value": menu_images, "source": source})
            stats["menu_images_candidates"] += 1

    for row in _read_csv(accommodation_path):
        entity_id = row.get("id", "")
        if not entity_id:
            stats["accommodation_invalid_rows"] += 1
            continue
        expected_types[entity_id] = "Accommodation"
        source = row.get("link") or ACCOMMODATION_SOURCE
        sources = _sources(row.get("sources", ""))
        if sources:
            properties.append({"entity_id": entity_id, "key": "sources", "value": sources, "source": source})
            properties.append(
                {
                    "entity_id": entity_id,
                    "key": "source_count",
                    "value": str(len(json.loads(sources))),
                    "source": source,
                }
            )
            stats["sources_candidates"] += 1
            stats["source_count_candidates"] += 1

    return properties, expected_types, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-csv", type=Path, required=True)
    parser.add_argument("--accommodation-csv", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()
    if args.apply and args.delete:
        parser.error("--apply and --delete are mutually exclusive")

    with SessionLocal() as db:
        if args.delete:
            result = db.execute(delete(KnowledgeProperty).where(KnowledgeProperty.note == BATCH_MARKER))
            db.commit()
            print(json.dumps({"deleted": result.rowcount, "batchMarker": BATCH_MARKER}))
            return

        rows, expected_types, stats = _candidate_rows(args.restaurant_csv, args.accommodation_csv)
        entities = {
            entity.id: entity.entity_type
            for entity in db.scalars(
                select(KnowledgeEntity).where(KnowledgeEntity.id.in_(expected_types))
            )
        }
        missing_ids = sorted(set(expected_types) - set(entities))
        type_mismatches = sorted(
            entity_id
            for entity_id, actual_type in entities.items()
            if actual_type != expected_types[entity_id]
        )
        valid_ids = set(entities) - set(type_mismatches)
        valid_rows = [row for row in rows if row["entity_id"] in valid_ids]
        existing = db.execute(
            select(KnowledgeProperty.entity_id, KnowledgeProperty.key).where(
                KnowledgeProperty.entity_id.in_(valid_ids),
                KnowledgeProperty.key.in_({"price", "menu_images", "source_count", "sources"}),
            )
        ).all()

        report = {
            "mode": "apply" if args.apply else "dry-run",
            "batchMarker": BATCH_MARKER,
            "csvEntityIds": len(expected_types),
            "matchedEntityIds": len(valid_ids),
            "missingEntityIds": len(missing_ids),
            "missingEntityIdSample": missing_ids[:20],
            "typeMismatches": len(type_mismatches),
            "typeMismatchSample": type_mismatches[:20],
            "existingTargetProperties": len(existing),
            "candidateProperties": len(rows),
            "validProperties": len(valid_rows),
            **dict(stats),
        }
        if args.apply:
            write_time = datetime.now(timezone.utc).replace(tzinfo=None)
            for index in range(0, len(valid_rows), WRITE_BATCH_SIZE):
                batch = [
                    {**row, "note": BATCH_MARKER, "updated_at": write_time}
                    for row in valid_rows[index:index + WRITE_BATCH_SIZE]
                ]
                statement = postgres_insert(KnowledgeProperty).values(batch)
                db.execute(
                    statement.on_conflict_do_update(
                        index_elements=["entity_id", "key"],
                        set_={
                            "value": statement.excluded.value,
                            "source": statement.excluded.source,
                            "note": statement.excluded.note,
                            "updated_at": statement.excluded.updated_at,
                        },
                    )
                )
            db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
