#!/usr/bin/env python3
"""Soft-quarantine invalid active Knowledge Graph place records."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.research.schema import PLACE_TYPES  # noqa: E402
from app.modules.places.eligibility import (  # noqa: E402
    valid_canonical_place_name,
    valid_place_coordinates,
    valid_place_type,
)


PROPERTY_BATCH_SIZE = 1_000


def invalid_reasons(
    *,
    name: str,
    place_type: str | None,
    latitude: str | None,
    longitude: str | None,
) -> list[str]:
    reasons: list[str] = []
    if not valid_canonical_place_name(name):
        reasons.append("invalid_canonical_name")
    if not valid_place_type(place_type):
        reasons.append("invalid_place_type")
    if not valid_place_coordinates(latitude, longitude):
        reasons.append("invalid_coordinates")
    return reasons


def _load_candidates(
    db: Session,
) -> list[tuple[KnowledgeEntity, list[str]]]:
    entities = list(
        db.scalars(
            select(KnowledgeEntity)
            .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
            .order_by(KnowledgeEntity.id)
        )
    )
    properties: dict[str, dict[str, str]] = {
        entity.id: {} for entity in entities
    }
    entity_ids = list(properties)
    for index in range(0, len(entity_ids), PROPERTY_BATCH_SIZE):
        entity_id_batch = entity_ids[index:index + PROPERTY_BATCH_SIZE]
        for prop in db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id.in_(entity_id_batch)
            )
        ):
            properties[prop.entity_id][prop.key] = prop.value

    candidates: list[tuple[KnowledgeEntity, list[str]]] = []
    for entity in entities:
        props = properties[entity.id]
        if (props.get("catalog_status") or "active") != "active":
            continue
        reasons = invalid_reasons(
            name=entity.canonical_name,
            place_type=(
                props.get("place_type")
                or props.get("place_category")
                or entity.entity_type
            ),
            latitude=props.get("latitude"),
            longitude=props.get("longitude"),
        )
        if reasons:
            candidates.append((entity, reasons))
    return candidates


def _upsert_property(
    db: Session,
    entity_id: str,
    key: str,
    value: str,
    *,
    source: str,
) -> None:
    prop = db.scalar(
        select(KnowledgeProperty).where(
            KnowledgeProperty.entity_id == entity_id,
            KnowledgeProperty.key == key,
        )
    )
    if prop is None:
        db.add(
            KnowledgeProperty(
                entity_id=entity_id,
                key=key,
                value=value,
                source=source,
            )
        )
    else:
        prop.value = value
        prop.source = source


def apply_quarantine(
    db: Session,
    candidates: list[tuple[KnowledgeEntity, list[str]]],
) -> None:
    source = "script:quarantine_invalid_knowledge_graph_places"
    quarantined_at = datetime.now(timezone.utc).isoformat()
    for entity, reasons in candidates:
        for key, value in (
            ("catalog_status", "quarantined"),
            ("quarantine_reasons", json.dumps(reasons, ensure_ascii=False)),
            ("quarantined_at", quarantined_at),
        ):
            _upsert_property(db, entity.id, key, value, source=source)
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        candidates = _load_candidates(db)
        reason_counts = Counter(
            reason for _, reasons in candidates for reason in reasons
        )
        print(
            json.dumps(
                {
                    "candidateCount": len(candidates),
                    "reasonCounts": dict(sorted(reason_counts.items())),
                    "sample": [
                        {
                            "entityId": entity.id,
                            "name": entity.canonical_name,
                            "reasons": reasons,
                        }
                        for entity, reasons in candidates[:20]
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.apply:
            apply_quarantine(db, candidates)
            print(f"Quarantined {len(candidates)} invalid active places.")


if __name__ == "__main__":
    main()
