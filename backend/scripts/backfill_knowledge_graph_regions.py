#!/usr/bin/env python3
"""Backfill city/province region keys from source-backed Google Maps addresses.

Dry-run is the default. ``--apply`` writes only when the active place has a
Google Maps source URL and exactly one recognized current province/city name in
its source address. Ambiguous or placeholder addresses remain ``vn,unmapped``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

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
from app.modules.knowledge_graph.text import normalize_knowledge_text  # noqa: E402


OFFICIAL_ADMIN_REFERENCE = "https://chinhphu.vn/thong-tin-tinh-thanh"
GOOGLE_MAPS_HOSTS = {"google.com", "www.google.com", "maps.google.com"}

# Conservative allowlist: only current province/city names actually observed
# in the current unmapped catalog. Additions require an official reference and
# regression test instead of accepting arbitrary comma-separated address text.
ADMIN_REGION_ALIASES = {
    "ha noi": "vn,ha-noi",
    "hanoi": "vn,ha-noi",
    "hung yen": "vn,hung-yen",
    "phu tho": "vn,phu-tho",
    "thanh hoa": "vn,thanh-hoa",
    "ha tinh": "vn,ha-tinh",
    "quang ninh": "vn,quang-ninh",
    "thai nguyen": "vn,thai-nguyen",
}
PLACEHOLDER_ADDRESSES = {
    "",
    "chua co dia chi trong du lieu nguon",
    "unknown",
    "unspecified",
}
PROPERTY_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class RegionBackfillDecision:
    entity_id: str
    name: str
    region_key: str
    matched_admin_area: str
    address: str
    source_url: str


def _normalized_component(value: str) -> str:
    normalized = normalize_knowledge_text(value)
    normalized = re.sub(r"\b\d{4,6}\b", "", normalized)
    normalized = re.sub(r"^(?:thanh pho|tinh|tp)\s+", "", normalized)
    return " ".join(normalized.split())


def region_from_source_address(address: str) -> tuple[str, str] | None:
    if normalize_knowledge_text(address) in PLACEHOLDER_ADDRESSES:
        return None
    matches = {
        (ADMIN_REGION_ALIASES[component], component)
        for raw_component in address.split(",")
        if (component := _normalized_component(raw_component))
        in ADMIN_REGION_ALIASES
    }
    region_keys = {region_key for region_key, _ in matches}
    if len(region_keys) != 1:
        return None
    region_key = next(iter(region_keys))
    matched = sorted(
        component for candidate_region, component in matches
        if candidate_region == region_key
    )[0]
    return region_key, matched


def _is_google_maps_source(platform: str, source_url: str) -> bool:
    host = (urlparse(source_url).hostname or "").casefold()
    return platform.casefold() == "google_maps" and host in GOOGLE_MAPS_HOSTS


def load_decisions(db: Session) -> tuple[list[RegionBackfillDecision], dict[str, int]]:
    entities = list(
        db.scalars(
            select(KnowledgeEntity)
            .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
            .order_by(KnowledgeEntity.id)
        )
    )
    entity_ids = [entity.id for entity in entities]
    properties: dict[str, dict[str, str]] = {
        entity_id: {} for entity_id in entity_ids
    }
    for index in range(0, len(entity_ids), PROPERTY_BATCH_SIZE):
        entity_id_batch = entity_ids[index:index + PROPERTY_BATCH_SIZE]
        for prop in db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id.in_(entity_id_batch)
            )
        ):
            properties[prop.entity_id][prop.key] = prop.value

    decisions: list[RegionBackfillDecision] = []
    counters = {
        "activeUnmapped": 0,
        "missingTrustedSource": 0,
        "unrecognizedOrAmbiguousAddress": 0,
    }
    for entity in entities:
        props = properties[entity.id]
        if (props.get("catalog_status") or "active") != "active":
            continue
        if (props.get("region_key") or "vn,unmapped") != "vn,unmapped":
            continue
        counters["activeUnmapped"] += 1
        address = props.get("address") or ""
        platform = props.get("source_platform") or ""
        source_url = props.get("source_url") or ""
        if not _is_google_maps_source(platform, source_url):
            counters["missingTrustedSource"] += 1
            continue
        match = region_from_source_address(address)
        if match is None:
            counters["unrecognizedOrAmbiguousAddress"] += 1
            continue
        region_key, matched_admin_area = match
        decisions.append(
            RegionBackfillDecision(
                entity_id=entity.id,
                name=entity.canonical_name,
                region_key=region_key,
                matched_admin_area=matched_admin_area,
                address=address,
                source_url=source_url,
            )
        )
    return decisions, counters


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


def apply_decisions(db: Session, decisions: list[RegionBackfillDecision]) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    source = "script:backfill_knowledge_graph_regions"
    for decision in decisions:
        evidence = json.dumps(
            {
                "address": decision.address,
                "matchedAdminArea": decision.matched_admin_area,
                "provider": "google_maps",
                "sourceUrl": decision.source_url,
                "officialAdminReference": OFFICIAL_ADMIN_REFERENCE,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for key, value in (
            ("region_key", decision.region_key),
            ("region_key_source", "google_maps_address"),
            ("region_key_source_url", decision.source_url),
            ("region_key_confidence", "high"),
            ("region_key_evidence", evidence),
            ("region_key_updated_at", updated_at),
        ):
            _upsert_property(db, decision.entity_id, key, value, source=source)
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        decisions, counters = load_decisions(db)
        by_region: dict[str, int] = {}
        for decision in decisions:
            by_region[decision.region_key] = by_region.get(decision.region_key, 0) + 1
        print(json.dumps({**counters, "eligible": len(decisions), "byRegion": by_region}, ensure_ascii=False, indent=2))
        if args.apply:
            apply_decisions(db, decisions)
            print(f"Applied {len(decisions)} source-backed regionKey updates.")


if __name__ == "__main__":
    main()
