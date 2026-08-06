#!/usr/bin/env python3
"""Backfill clear Planner categories from provider place types."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, aliased


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.research.schema import PLACE_TYPES  # noqa: E402
from app.modules.places.category import canonical_place_category  # noqa: E402


WRITE_BATCH_SIZE = 500
SOURCE = "script:backfill_knowledge_graph_categories:v2"
CANONICAL_CATEGORIES = frozenset(
    {
        "adventure",
        "attraction",
        "beach",
        "cafe",
        "cemetery",
        "culture",
        "family",
        "food",
        "hotel",
        "nature",
        "nightlife",
        "other",
        "shopping",
        "transport",
        "wellness",
    }
)


def classify_candidate(properties: dict[str, str], entity_type: str) -> str | None:
    current = (properties.get("place_category") or "").strip().casefold()
    if current in CANONICAL_CATEGORIES and current != "other":
        return None
    place_type = (properties.get("place_type") or current or entity_type).strip()
    mapped = canonical_place_category(place_type)
    return mapped if mapped != "other" else None


def load_candidates(
    db: Session,
) -> list[tuple[KnowledgeEntity, dict[str, str], str]]:
    catalog_status = aliased(KnowledgeProperty)
    place_category = aliased(KnowledgeProperty)
    place_type = aliased(KnowledgeProperty)
    rows = db.execute(
        select(
            KnowledgeEntity,
            catalog_status.value,
            place_category.value,
            place_type.value,
        )
        .outerjoin(
            catalog_status,
            and_(
                catalog_status.entity_id == KnowledgeEntity.id,
                catalog_status.key == "catalog_status",
            ),
        )
        .outerjoin(
            place_category,
            and_(
                place_category.entity_id == KnowledgeEntity.id,
                place_category.key == "place_category",
            ),
        )
        .outerjoin(
            place_type,
            and_(
                place_type.entity_id == KnowledgeEntity.id,
                place_type.key == "place_type",
            ),
        )
        .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
        .order_by(KnowledgeEntity.id)
    )
    candidates = []
    for entity, status, category, provider_type in rows:
        if (status or "active") != "active":
            continue
        props = {
            key: value
            for key, value in (
                ("catalog_status", status),
                ("place_category", category),
                ("place_type", provider_type),
            )
            if value is not None
        }
        mapped = classify_candidate(props, entity.entity_type)
        if mapped:
            candidates.append((entity, props, mapped))
    return candidates


def apply_candidates(
    db: Session,
    candidates: list[tuple[KnowledgeEntity, dict[str, str], str]],
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []
    for entity, props, category in candidates:
        current = (props.get("place_category") or "").strip()
        if (
            not props.get("place_type")
            and current.casefold() not in CANONICAL_CATEGORIES
        ):
            rows.append(
                {"entity_id": entity.id, "key": "place_type", "value": current}
            )
        rows.extend(
            (
                {"entity_id": entity.id, "key": "place_category", "value": category},
                {"entity_id": entity.id, "key": "place_category_source", "value": SOURCE},
                {
                    "entity_id": entity.id,
                    "key": "place_category_updated_at",
                    "value": updated_at,
                },
            )
        )
    write_time = datetime.now(timezone.utc).replace(tzinfo=None)
    for index in range(0, len(rows), WRITE_BATCH_SIZE):
        batch = [
            {**row, "source": SOURCE, "updated_at": write_time}
            for row in rows[index:index + WRITE_BATCH_SIZE]
        ]
        statement = postgres_insert(KnowledgeProperty).values(batch)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["entity_id", "key"],
                set_={
                    "value": statement.excluded.value,
                    "source": statement.excluded.source,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        )
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        candidates = load_candidates(db)
        by_category = Counter(category for _, _, category in candidates)
        by_type = Counter(
            (props.get("place_type") or entity.entity_type, category)
            for entity, props, category in candidates
        )
        print(
            json.dumps(
                {
                    "candidateCount": len(candidates),
                    "byCategory": dict(sorted(by_category.items())),
                    "topTypes": [
                        {"placeType": place_type, "category": category, "count": count}
                        for (place_type, category), count in by_type.most_common(30)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.apply:
            apply_candidates(db, candidates)
            print(f"Updated {len(candidates)} active place categories.")


if __name__ == "__main__":
    main()
