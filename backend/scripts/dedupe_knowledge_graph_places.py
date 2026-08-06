#!/usr/bin/env python3
"""Find and soft-merge duplicate Knowledge Graph places.

The command is dry-run by default and writes exactly two reports:

* ``auto_merge.json`` for conservative, deterministic merge groups.
* ``needs_review.json`` for identity collisions that must not be auto-applied.

``--apply`` never deletes an entity.  It copies names to the canonical entity as
searchable aliases and marks secondary entities with ``catalog_status=merged``
plus ``merged_into_entity_id``.  Existing foreign keys therefore remain valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.place_repository import (  # noqa: E402
    KnowledgeGraphPlaceRepository,
)
from app.modules.knowledge_graph.text import normalize_knowledge_text  # noqa: E402
from app.modules.places.category import canonical_place_category  # noqa: E402


DEFAULT_OUTPUT_DIR = BACKEND_DIR / "var" / "place-dedupe"
SEARCHABLE_ALIAS_STATUSES = {"imported", "verified", "active", "approved"}
BRANCH_CATEGORIES = {"cafe", "food", "hotel", "nightlife", "shopping"}
GENERIC_KEYS = {
    "banh mi",
    "bun cha",
    "bun dau",
    "cafe",
    "coffee",
    "hotel",
    "pho",
    "quan an",
    "quan com binh dan",
    "restaurant",
}
PLACEHOLDER_TYPES = {"", "nan", "none", "null", "unknown", "unspecified"}
# Reviewed against the current provider identities, addresses and coordinates.
# These are one physical landmark represented by English/Vietnamese catalog rows.
CURATED_AUTO_MERGES = (
    {
        "canonicalEntityId": "travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg",
        "secondaryEntityIds": (
            "travel_place_ChIJ-XT4UgCrNTERKZxxsb_mr1Q",
            "travel_place_ChIJ7XGFbQCrNTERf97jL8xTmz4",
            "travel_place_ChIJjZMwSwCrNTERGyXODX2OY1k",
        ),
        "reason": "curated_same_landmark_temple_of_literature",
    },
    {
        "canonicalEntityId": "travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE",
        "secondaryEntityIds": ("travel_place_ChIJ9enuawCrNTER_MKcOfib7o8",),
        "reason": "curated_same_landmark_hoan_kiem_lake",
    },
    {
        "canonicalEntityId": "travel_place_ChIJfyTf5o6rNTER6dKWJmY9GOY",
        "secondaryEntityIds": (
            "travel_place_ChIJ-0sNU46rNTERkEawQmf-umM",
            "travel_place_ChIJM9-GBQCrNTERKtnxiEaGfXk",
        ),
        "reason": "curated_same_landmark_thong_nhat_park",
    },
    {
        "canonicalEntityId": "travel_place_ChIJBdI0eZqrNTEREK_Nhl4hGOI",
        "secondaryEntityIds": ("travel_place_ChIJoVlor5CrNTERf6I8-qVIqvw",),
        "reason": "curated_same_landmark_hanoi_railway_station",
    },
    {
        "canonicalEntityId": "travel_place_ChIJawZgcv6qNTER26OqCYOYLEw",
        "secondaryEntityIds": ("travel_place_ChIJfdCEMgCrNTER1-pDHVYfrWg",),
        "reason": "curated_same_landmark_west_lake",
    },
    {
        "canonicalEntityId": "accommodation_ChIJMRkwx1OqNTER7eOiQTdjYz0",
        "secondaryEntityIds": ("accommodation_ChIJMRkwx1OqNTERmtvxcvDaOy4",),
        "reason": "curated_exact_duplicate_same_villa_coordinates",
    },
    {
        "canonicalEntityId": "accommodation_ChIJbQ4SxzqrNTERdUZexfQVBcA",
        "secondaryEntityIds": ("travel_place_ChIJ5S3buDqrNTER_XtHdSsC72Y",),
        "reason": "curated_same_serviced_residence_somerset_hoa_binh",
    },
    {
        "canonicalEntityId": "accommodation_ChIJee5gzPCrNTER8lD4jsGnAgk",
        "secondaryEntityIds": ("travel_place_ChIJWzInghqrNTERfBPwzqkgCQA",),
        "reason": "curated_same_hotel_parkroyal_serviced_suites",
    },
    {
        "canonicalEntityId": "accommodation_ChIJuSiTcM-rNTERCqf9dC9Kc0g",
        "secondaryEntityIds": ("travel_place_ChIJJWJpLQ-rNTERz-Pxg_3dam4",),
        "reason": "curated_same_homestay_lilos",
    },
    {
        "canonicalEntityId": "drink_dessert_ChIJ6VTf4g2pNTERmHDntrvBhLY",
        "secondaryEntityIds": ("drink_dessert_ChIJLZmNA2KpNTERBCNYSfeotVg",),
        "reason": "curated_same_coffee_shop_same_address",
    },
    {
        "canonicalEntityId": "drink_dessert_ChIJBaHJ9MCrNTEReQQvavIQoaE",
        "secondaryEntityIds": ("travel_place_ChIJewPMTACrNTERIh--FIOjspE",),
        "reason": "curated_same_karaoke_fantasy",
    },
    {
        "canonicalEntityId": "restaurant_ChIJxbUH5LmrNTERZkgJnAK0riU",
        "secondaryEntityIds": ("drink_dessert_ChIJU_xHpMmfNTERijPaWA6Vpt4",),
        "reason": "curated_same_banh_cuon_ba_xuan",
    },
    {
        "canonicalEntityId": "travel_place_ChIJDTZhSQBVNDERqTEX3jshUMI",
        "secondaryEntityIds": ("travel_place_ChIJWe-DGwBVNDER7u5GFBSql6Y",),
        "reason": "curated_exact_duplicate_xuong_laser_gw",
    },
    {
        "canonicalEntityId": "travel_place_ChIJoazA3ipTNDERcMdktbY2yg8",
        "secondaryEntityIds": ("travel_place_ChIJC7qTf_JSNDER7nTLuU53CCY",),
        "reason": "curated_same_yen_nghia_bus_station",
    },
    {
        "canonicalEntityId": "travel_place_ChIJ_8OSWgCrNTERUjH5ICI4pW8",
        "secondaryEntityIds": ("travel_place_ChIJh0TC5rirNTER5hfy54P03tk",),
        "reason": "curated_same_dong_xuan_market",
    },
    {
        "canonicalEntityId": "travel_place_ChIJ8WJDcbatNTERChhhzuQTfT0",
        "secondaryEntityIds": (
            "travel_place_ChIJGwtKF8CrNTERaD2UOze7O18",
            "travel_place_ChIJRT0kF8CrNTERpQUSbHCqLbs",
        ),
        "reason": "curated_same_tuong_dai_cam_tu",
    },
    {
        "canonicalEntityId": "travel_place_ChIJZ52Cqr-rNTER818BbjbO4GQ",
        "secondaryEntityIds": ("travel_place_ChIJG0AdPNGqNTERB1y64YumnIo",),
        "reason": "curated_same_chua_khu_nhang",
    },
    {
        "canonicalEntityId": "travel_place_ChIJSwqMUquvNTERj_Qr6odZXaw",
        "secondaryEntityIds": ("travel_place_ChIJI1-imIOuNTER7KWbNmdZVsM",),
        "reason": "curated_same_den_tho_ba_nguyen_thi_lo",
    },
    {
        "canonicalEntityId": "travel_place_ChIJq2p4wQRSNDERn19YEyFptcI",
        "secondaryEntityIds": ("travel_place_ChIJIW8RZwNSNDERH9J9VzuOqT8",),
        "reason": "curated_same_nui_tram_landmark",
    },
    {
        "canonicalEntityId": "travel_place_ChIJPZtJXMqpNTERdXOAoN10kPE",
        "secondaryEntityIds": ("travel_place_ChIJTWyQcwCpNTERY8bxckoHQDA",),
        "reason": "curated_exact_duplicate_alux_showroom",
    },
    {
        "canonicalEntityId": "travel_place_ChIJf1QiqCirNTERwG2i_CuaPqg",
        "secondaryEntityIds": ("travel_place_ChIJlYDRNwCrNTERETjtcRRltQc",),
        "reason": "curated_exact_duplicate_mit_art",
    },
    {
        "canonicalEntityId": "travel_place_ChIJQ91rWI2rNTERGvtYIM8Tk3w",
        "secondaryEntityIds": ("travel_place_ChIJrZVpWI2rNTERAkD5rggAyAo",),
        "reason": "curated_exact_duplicate_apartment_listing",
    },
    {
        "canonicalEntityId": "travel_place_ChIJSf2gG76rNTER2xOzPFt78ho",
        "secondaryEntityIds": ("travel_place_ChIJSf2gG76rNTERCOBX5fymipU",),
        "reason": "curated_exact_duplicate_centre_alley_house",
    },
    {
        "canonicalEntityId": "travel_place_ChIJoR8SgOqrNTER4y-GMiMIpXs",
        "secondaryEntityIds": ("travel_place_ChIJoR8SgOqrNTERkMx47VkK47w",),
        "reason": "curated_exact_duplicate_kolor_home",
    },
    {
        "canonicalEntityId": "travel_place_ChIJfYngSACrNTER3RS5reuEuIA",
        "secondaryEntityIds": ("travel_place_ChIJmf-c3qGrNTERwCNwxmiU_Gg",),
        "reason": "curated_same_vuon_hoa_le_truc",
    },
    {
        "canonicalEntityId": "travel_place_ChIJOZY3fyKtNTERpFzHGptwLRI",
        "secondaryEntityIds": ("travel_place_ChIJWRPkgRitNTERtbjQ17DnjKg",),
        "reason": "curated_same_be_boi_dai_thanh",
    },
    {
        "canonicalEntityId": "travel_place_ChIJ7UmdcQCtNTEROFEaXuOGQcA",
        "secondaryEntityIds": ("travel_place_ChIJg-0ZIQ-sNTERNliuyNF0Pg0",),
        "reason": "curated_same_cho_quynh_mai",
    },
    {
        "canonicalEntityId": "travel_place_ChIJ7bB-FhtVNDERx1neXAWOqT0",
        "secondaryEntityIds": ("travel_place_ChIJN9MnOclUNDERpkIjfqBXqx8",),
        "reason": "curated_same_cho_dong_xa",
    },
    {
        "canonicalEntityId": "travel_place_ChIJBcsm6CerNTEROJk3_MIw9Mw",
        "secondaryEntityIds": ("travel_place_ChIJUbIGljCrNTERLBY3VnufQus",),
        "reason": "curated_same_lotte_mall_west_lake",
    },
)
MEANINGLESS_ADDRESS_TOKENS = {
    "duong",
    "street",
    "road",
    "vietnam",
    "viet",
    "nam",
    "hanoi",
    "noi",
}


@dataclass(frozen=True)
class PlaceRecord:
    id: str
    name: str
    normalized_name: str
    entity_type: str
    place_type: str
    address: str
    city: str
    region_key: str
    latitude: float
    longitude: float
    data_confidence: str
    review_count: int
    revision: int
    aliases: tuple[str, ...]

    @property
    def category(self) -> str:
        return canonical_place_category(self.place_type)

    @property
    def identity_keys(self) -> set[str]:
        values = [self.name, *self.aliases]
        return {
            key
            for value in values
            if (key := normalize_knowledge_text(value)) and len(key) >= 3
        }


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply auto_merge.json using soft-merge semantics.")
    parser.add_argument(
        "--dismiss-different-addresses",
        action="store_true",
        help="Mark review groups with clearly different populated addresses as not merged and remove them from needs_review.json.",
    )
    parser.add_argument(
        "--process-review-and-clean",
        action="store_true",
        help="Merge review groups whose populated addresses are all similar, mark the rest not merged, then delete place-dedupe JSON reports.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--auto-merge-file", type=Path, default=None)
    return parser.parse_args()


def addresses_need_manual_review(addresses: list[str]) -> bool:
    """Return True when at least two populated addresses are equal/near-equal."""
    normalized = [normalize_knowledge_text(address) for address in addresses]
    populated = [address for address in normalized if address]
    if len(populated) < 2:
        return True
    for index, left in enumerate(populated):
        for right in populated[index + 1 :]:
            if left == right:
                return True
            shared_numbers = _address_numbers(left).intersection(_address_numbers(right))
            shared_tokens = _tokens(left).intersection(_tokens(right))
            if shared_numbers and len(shared_tokens) >= 2:
                return True
    return False


def addresses_are_all_similar(addresses: list[str]) -> bool:
    normalized = [normalize_knowledge_text(address) for address in addresses]
    populated = [address for address in normalized if address]
    if len(populated) < 2:
        return False
    for index, left in enumerate(populated):
        for right in populated[index + 1 :]:
            if left == right:
                continue
            shared_numbers = _address_numbers(left).intersection(_address_numbers(right))
            shared_tokens = _tokens(left).intersection(_tokens(right))
            if not (shared_numbers and len(shared_tokens) >= 2):
                return False
    return True


def dismiss_different_address_groups(db: Session, report: dict) -> int:
    dismissed = 0
    remaining = []
    for group in report.get("groups", []):
        addresses = [str(record.get("address", "")) for record in group.get("records", [])]
        if addresses_need_manual_review(addresses):
            remaining.append(group)
            continue
        anchor_id = next(
            (record.get("entityId") for record in group.get("records", []) if record.get("entityId")),
            None,
        )
        if not anchor_id:
            remaining.append(group)
            continue
        prop = db.scalar(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == anchor_id,
                KnowledgeProperty.key == "dedupe_review_decisions",
            )
        )
        values: list[str] = []
        if prop is not None:
            try:
                loaded = json.loads(prop.value)
                if isinstance(loaded, list):
                    values = [str(value) for value in loaded]
            except (TypeError, ValueError):
                pass
        group_id = str(group.get("groupId"))
        if group_id not in values:
            values.append(group_id)
        if prop is None:
            db.add(
                KnowledgeProperty(
                    entity_id=anchor_id,
                    key="dedupe_review_decisions",
                    value=json.dumps(values),
                    source="admin:place-dedupe-review",
                )
            )
        else:
            prop.value = json.dumps(values)
            prop.source = "admin:place-dedupe-review"
        dismissed += 1
    report["groups"] = remaining
    report["groupCount"] = len(remaining)
    db.commit()
    return dismissed


def _tokens(value: str) -> set[str]:
    normalized = normalize_knowledge_text(value)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in MEANINGLESS_ADDRESS_TOKENS
    }


def _address_numbers(value: str) -> set[str]:
    return set(re.findall(r"\b\d+[a-z]?\b", normalize_knowledge_text(value)))


def _distance_km(left: PlaceRecord, right: PlaceRecord) -> float:
    latitude_delta = math.radians(right.latitude - left.latitude)
    longitude_delta = math.radians(right.longitude - left.longitude)
    left_latitude = math.radians(left.latitude)
    right_latitude = math.radians(right.latitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(left_latitude)
        * math.cos(right_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 6_371.0 * 2 * math.asin(math.sqrt(value))


def _addresses_compatible(left: PlaceRecord, right: PlaceRecord) -> bool:
    left_key = normalize_knowledge_text(left.address)
    right_key = normalize_knowledge_text(right.address)
    if left_key and left_key == right_key:
        return True
    shared_numbers = _address_numbers(left.address).intersection(
        _address_numbers(right.address)
    )
    shared_tokens = _tokens(left.address).intersection(_tokens(right.address))
    return bool(shared_numbers and len(shared_tokens) >= 2)


def _types_compatible(left: PlaceRecord, right: PlaceRecord) -> bool:
    if normalize_knowledge_text(left.place_type) == normalize_knowledge_text(
        right.place_type
    ):
        return True
    return left.category != "other" and left.category == right.category


def _pair_auto_merge_reason(
    left: PlaceRecord,
    right: PlaceRecord,
) -> tuple[bool, str, float]:
    distance = _distance_km(left, right)
    if not _types_compatible(left, right):
        return False, "incompatible_place_type", distance
    if left.category == "other" and right.category == "other":
        return False, "unclassified_place_type", distance

    left_address = normalize_knowledge_text(left.address)
    right_address = normalize_knowledge_text(right.address)
    shared_keys = left.identity_keys.intersection(right.identity_keys)
    # Any populated address is a manual-review signal. A mismatch can indicate
    # a branch, while a match can still represent two venues in one building.
    if left_address and right_address:
        if left_address == right_address or _addresses_compatible(left, right):
            return False, "address_match_needs_manual_review", distance
        return False, "address_mismatch_needs_manual_review", distance
    if not shared_keys:
        return False, "no_shared_canonical_or_alias", distance
    if any(key in GENERIC_KEYS for key in shared_keys):
        return False, "generic_name", distance

    category = left.category
    if category in BRANCH_CATEGORIES:
        if distance > 0.05:
            return False, "possible_branch_distance", distance
        if not _addresses_compatible(left, right):
            return False, "possible_branch_address", distance
        return True, "same_branch_name_address_within_50m", distance

    maximum_distance = 0.4 if category in {"attraction", "culture", "nature"} else 0.2
    if distance > maximum_distance:
        return False, "same_name_but_too_far", distance
    canonical_exact = left.normalized_name == right.normalized_name
    if not canonical_exact and not _addresses_compatible(left, right):
        return False, "alias_match_without_address", distance
    return True, "same_identity_within_distance", distance


def _quality(record: PlaceRecord) -> tuple[int, int, int, int, int, str]:
    return (
        int(record.region_key not in {"", "vn,unmapped"}),
        int(normalize_knowledge_text(record.place_type) not in PLACEHOLDER_TYPES),
        {"low": 1, "medium": 2, "high": 3}.get(record.data_confidence, 0),
        record.review_count,
        record.revision,
        record.id,
    )


def _record_payload(record: PlaceRecord) -> dict:
    return {
        "entityId": record.id,
        "name": record.name,
        "aliases": list(record.aliases),
        "placeType": record.place_type,
        "category": record.category,
        "address": record.address,
        "regionKey": record.region_key,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "reviewCount": record.review_count,
        "revision": record.revision,
    }


def _fingerprint(records: list[PlaceRecord]) -> str:
    material = "\n".join(
        f"{record.id}|{record.revision}|{record.normalized_name}|{record.region_key}"
        for record in sorted(records, key=lambda item: item.id)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _group_id(prefix: str, records: Iterable[PlaceRecord]) -> str:
    material = "|".join(sorted(record.id for record in records))
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}"


def load_records(db: Session) -> list[PlaceRecord]:
    projected = KnowledgeGraphPlaceRepository(db).list_active_for_planner_research(
        limit=100_000
    )
    return [
        PlaceRecord(
            id=record.id,
            name=record.name,
            normalized_name=normalize_knowledge_text(record.name),
            entity_type=record.place_type,
            place_type=record.place_type,
            address=record.address or "",
            city=record.city or "",
            region_key=record.region_key or "",
            latitude=float(record.latitude),
            longitude=float(record.longitude),
            data_confidence=record.data_confidence,
            review_count=int(record.review_count or 0),
            revision=int(record.revision or 1),
            aliases=tuple(
                value
                for value in record.metadata_json.get("aliases", [])
                if isinstance(value, str) and value.strip()
            ),
        )
        for record in projected
        if record.latitude is not None
        and record.longitude is not None
        and not (
            float(record.latitude) == 0.0 and float(record.longitude) == 0.0
        )
    ]


def build_reports(records: list[PlaceRecord]) -> tuple[dict, dict]:
    records_by_id = {record.id: record for record in records}
    identity_index: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for key in record.identity_keys:
            identity_index[key].add(record.id)

    collision_keys = {
        key: ids for key, ids in identity_index.items() if len(ids) > 1
    }
    union = UnionFind(records_by_id)
    for ids in collision_keys.values():
        ordered = sorted(ids)
        for entity_id in ordered[1:]:
            union.union(ordered[0], entity_id)

    components: dict[str, list[PlaceRecord]] = defaultdict(list)
    collision_ids = {entity_id for ids in collision_keys.values() for entity_id in ids}
    for entity_id in collision_ids:
        components[union.find(entity_id)].append(records_by_id[entity_id])

    auto_groups: list[dict] = []
    review_groups: list[dict] = []
    assigned_auto_ids: set[str] = set()
    for curated in CURATED_AUTO_MERGES:
        curated_ids = {
            curated["canonicalEntityId"],
            *curated["secondaryEntityIds"],
        }
        if not curated_ids.issubset(records_by_id):
            continue
        cluster = [records_by_id[entity_id] for entity_id in sorted(curated_ids)]
        distances = [
            _distance_km(left, right)
            for index, left in enumerate(cluster)
            for right in cluster[index + 1 :]
        ]
        auto_groups.append(
            {
                "groupId": _group_id("auto", cluster),
                "canonicalEntityId": curated["canonicalEntityId"],
                "secondaryEntityIds": sorted(curated["secondaryEntityIds"]),
                "confidence": "high",
                "reason": curated["reason"],
                "maximumDistanceKm": round(max(distances, default=0.0), 4),
                "records": [_record_payload(record) for record in cluster],
                "applied": False,
            }
        )
        assigned_auto_ids.update(curated_ids)

    for component in sorted(
        components.values(), key=lambda rows: min(record.id for record in rows)
    ):
        component = [
            record for record in component if record.id not in assigned_auto_ids
        ]
        if len(component) < 2:
            continue
        pair_union = UnionFind(record.id for record in component)
        pair_evidence: dict[tuple[str, str], dict] = {}
        rejected_reasons: set[str] = set()
        for index, left in enumerate(component):
            for right in component[index + 1 :]:
                allowed, reason, distance = _pair_auto_merge_reason(left, right)
                pair_evidence[tuple(sorted((left.id, right.id)))] = {
                    "distanceKm": round(distance, 4),
                    "reason": reason,
                    "autoMerge": allowed,
                }
                if allowed:
                    pair_union.union(left.id, right.id)
                else:
                    rejected_reasons.add(reason)

        auto_components: dict[str, list[PlaceRecord]] = defaultdict(list)
        for record in component:
            auto_components[pair_union.find(record.id)].append(record)
        component_auto_groups: list[str] = []
        for cluster in auto_components.values():
            if len(cluster) < 2:
                continue
            all_pairs_safe = all(
                pair_evidence[tuple(sorted((left.id, right.id)))]["autoMerge"]
                for index, left in enumerate(cluster)
                for right in cluster[index + 1 :]
            )
            if not all_pairs_safe or len(cluster) > 5:
                rejected_reasons.add("cluster_not_complete_or_too_large")
                continue
            canonical = max(cluster, key=_quality)
            group_id = _group_id("auto", cluster)
            component_auto_groups.append(group_id)
            assigned_auto_ids.update(record.id for record in cluster)
            distances = [
                pair_evidence[tuple(sorted((left.id, right.id)))]["distanceKm"]
                for index, left in enumerate(cluster)
                for right in cluster[index + 1 :]
            ]
            auto_groups.append(
                {
                    "groupId": group_id,
                    "canonicalEntityId": canonical.id,
                    "secondaryEntityIds": sorted(
                        record.id for record in cluster if record.id != canonical.id
                    ),
                    "confidence": "high",
                    "reason": "deterministic_identity_and_location_match",
                    "maximumDistanceKm": max(distances, default=0.0),
                    "records": [_record_payload(record) for record in sorted(cluster, key=lambda item: item.id)],
                    "applied": False,
                }
            )

        unresolved_records = [
            record for record in component if record.id not in assigned_auto_ids
        ]
        if unresolved_records or len(component_auto_groups) != 1:
            review_groups.append(
                {
                    "groupId": _group_id("review", component),
                    "reasonCodes": sorted(rejected_reasons) or ["identity_collision"],
                    "relatedAutoMergeGroupIds": component_auto_groups,
                    "records": [_record_payload(record) for record in sorted(component, key=lambda item: item.id)],
                }
            )

    generated_at = datetime.now(timezone.utc).isoformat()
    fingerprint = _fingerprint(records)
    common = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "databaseFingerprint": fingerprint,
    }
    return (
        {**common, "groupCount": len(auto_groups), "groups": auto_groups},
        {**common, "groupCount": len(review_groups), "groups": review_groups},
    )


def load_dismissed_review_group_ids(db: Session) -> set[str]:
    dismissed: set[str] = set()
    values = db.scalars(
        select(KnowledgeProperty.value).where(
            KnowledgeProperty.key == "dedupe_review_decisions"
        )
    )
    for value in values:
        try:
            decisions = json.loads(value)
        except (TypeError, ValueError):
            decisions = []
        if isinstance(decisions, list):
            dismissed.update(str(group_id) for group_id in decisions)
    return dismissed


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


def _copy_alias(
    db: Session,
    canonical_id: str,
    value: str,
    *,
    source: str,
    aliases_by_entity: dict[str, set[str]],
) -> None:
    cleaned = " ".join(value.split())
    if not cleaned:
        return
    existing_aliases = aliases_by_entity.get(canonical_id)
    if existing_aliases is None:
        existing_aliases = set(
            db.scalars(
                select(KnowledgeAlias.alias).where(
                    KnowledgeAlias.entity_id == canonical_id
                )
            )
        )
        aliases_by_entity[canonical_id] = existing_aliases
    if cleaned in existing_aliases:
        return
    db.add(
        KnowledgeAlias(
            entity_id=canonical_id,
            alias=cleaned,
            normalized_alias=normalize_knowledge_text(cleaned),
            language="und",
            alias_type="alternate_name",
            source=source,
            provider="knowledge_graph_dedupe",
            status="imported",
            confidence=1.0,
        )
    )
    existing_aliases.add(cleaned)


def apply_report(db: Session, report: dict, current_records: list[PlaceRecord]) -> int:
    if report.get("databaseFingerprint") != _fingerprint(current_records):
        raise RuntimeError("Database changed after dry-run; regenerate reports before apply.")
    records_by_id = {record.id: record for record in current_records}
    batch_id = f"kg-dedupe-{uuid.uuid4().hex[:12]}"
    aliases_by_entity: dict[str, set[str]] = {}
    applied = 0
    for group in report.get("groups", []):
        if group.get("applied") is True:
            continue
        canonical_id = group["canonicalEntityId"]
        secondary_ids = group["secondaryEntityIds"]
        if canonical_id not in records_by_id or any(
            entity_id not in records_by_id for entity_id in secondary_ids
        ):
            raise RuntimeError(f"Missing active entity in {group['groupId']}")
        source = f"script:dedupe_knowledge_graph_places:{batch_id}"
        canonical = records_by_id[canonical_id]
        merged_ids = set()
        existing_merged = db.scalar(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == canonical_id,
                KnowledgeProperty.key == "merged_from_entity_ids",
            )
        )
        if existing_merged is not None:
            try:
                merged_ids.update(json.loads(existing_merged.value))
            except (TypeError, ValueError):
                pass
        for secondary_id in secondary_ids:
            secondary = records_by_id[secondary_id]
            _copy_alias(
                db,
                canonical_id,
                secondary.name,
                source=source,
                aliases_by_entity=aliases_by_entity,
            )
            for alias in secondary.aliases:
                _copy_alias(
                    db,
                    canonical_id,
                    alias,
                    source=source,
                    aliases_by_entity=aliases_by_entity,
                )
            _upsert_property(db, secondary_id, "catalog_status", "merged", source=source)
            _upsert_property(
                db,
                secondary_id,
                "merged_into_entity_id",
                canonical_id,
                source=source,
            )
            _upsert_property(
                db,
                secondary_id,
                "merged_at",
                datetime.now(timezone.utc).isoformat(),
                source=source,
            )
            _upsert_property(db, secondary_id, "merge_batch_id", batch_id, source=source)
            merged_ids.add(secondary_id)
        _copy_alias(
            db,
            canonical_id,
            canonical.name,
            source=source,
            aliases_by_entity=aliases_by_entity,
        )
        _upsert_property(
            db,
            canonical_id,
            "merged_from_entity_ids",
            json.dumps(sorted(merged_ids), ensure_ascii=False),
            source=source,
        )
        group["applied"] = True
        group["mergeBatchId"] = batch_id
        applied += 1
    db.commit()
    return applied


def process_review_and_clean(
    db: Session,
    review_report: dict,
    current_records: list[PlaceRecord],
    output_dir: Path,
) -> tuple[int, int]:
    records_by_id = {record.id: record for record in current_records}
    merge_groups: list[dict] = []
    dismiss_groups: list[dict] = []
    for group in review_report.get("groups", []):
        records = [
            records_by_id[record["entityId"]]
            for record in group.get("records", [])
            if record.get("entityId") in records_by_id
        ]
        addresses = [record.address for record in records]
        if len(records) >= 2 and addresses_are_all_similar(addresses):
            canonical = max(records, key=_quality)
            secondary_ids = sorted(record.id for record in records if record.id != canonical.id)
            merge_groups.append(
                {
                    "groupId": group["groupId"],
                    "canonicalEntityId": canonical.id,
                    "secondaryEntityIds": secondary_ids,
                    "confidence": "admin_reviewed_address_match",
                    "reason": "admin_reviewed_similar_addresses",
                    "records": group.get("records", []),
                    "applied": False,
                }
            )
        else:
            dismiss_groups.append(group)

    applied = apply_report(
        db,
        {"databaseFingerprint": _fingerprint(current_records), "groups": merge_groups},
        current_records,
    ) if merge_groups else 0

    dismissed = 0
    for group in dismiss_groups:
        anchor_id = next(
            (record.get("entityId") for record in group.get("records", []) if record.get("entityId")),
            None,
        )
        if not anchor_id:
            continue
        prop = db.scalar(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == anchor_id,
                KnowledgeProperty.key == "dedupe_review_decisions",
            )
        )
        values: list[str] = []
        if prop is not None:
            try:
                loaded = json.loads(prop.value)
                if isinstance(loaded, list):
                    values = [str(value) for value in loaded]
            except (TypeError, ValueError):
                pass
        group_id = str(group.get("groupId"))
        if group_id not in values:
            values.append(group_id)
        if prop is None:
            db.add(
                KnowledgeProperty(
                    entity_id=anchor_id,
                    key="dedupe_review_decisions",
                    value=json.dumps(values),
                    source="admin:place-dedupe-review",
                )
            )
        else:
            prop.value = json.dumps(values)
            prop.source = "admin:place-dedupe-review"
        dismissed += 1
    db.commit()

    # The user explicitly requested removal of the generated reports after the
    # one-time batch decision has been persisted.
    for report_path in output_dir.glob("*.json"):
        report_path.unlink()
    return applied, dismissed


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    auto_path = args.auto_merge_file or output_dir / "auto_merge.json"
    review_path = output_dir / "needs_review.json"
    with SessionLocal() as db:
        if args.process_review_and_clean:
            review_report = json.loads(review_path.read_text(encoding="utf-8"))
            records = load_records(db)
            applied, dismissed = process_review_and_clean(
                db, review_report, records, output_dir
            )
            print(f"Applied {applied} similar-address review merges")
            print(f"Dismissed {dismissed} different-address review groups")
            print(f"Deleted place-dedupe JSON reports from {output_dir}")
            return
        if args.dismiss_different_addresses:
            review_report = json.loads(review_path.read_text(encoding="utf-8"))
            dismissed = dismiss_different_address_groups(db, review_report)
            review_report["generatedAt"] = datetime.now(timezone.utc).isoformat()
            write_report(review_path, review_report)
            print(f"Dismissed {dismissed} clearly different-address review groups")
            print(f"needs_review={review_report['groupCount']} -> {review_path}")
            return
        records = load_records(db)
        if args.apply:
            report = json.loads(auto_path.read_text(encoding="utf-8"))
            applied = apply_report(db, report, records)
            write_report(auto_path, report)
            print(f"Applied {applied} soft-merge groups from {auto_path}")
            return
        auto_report, review_report = build_reports(records)
        dismissed_group_ids = load_dismissed_review_group_ids(db)
        review_report["groups"] = [
            group
            for group in review_report["groups"]
            if group.get("groupId") not in dismissed_group_ids
        ]
        review_report["groupCount"] = len(review_report["groups"])
        if auto_path.exists():
            existing_report = json.loads(auto_path.read_text(encoding="utf-8"))
            applied_groups = [
                group
                for group in existing_report.get("groups", [])
                if group.get("applied") is True
            ]
            applied_id_sets = {
                frozenset(
                    [group["canonicalEntityId"], *group["secondaryEntityIds"]]
                )
                for group in applied_groups
            }
            pending_groups = [
                group
                for group in auto_report["groups"]
                if frozenset(
                    [group["canonicalEntityId"], *group["secondaryEntityIds"]]
                )
                not in applied_id_sets
            ]
            auto_report["groups"] = [*applied_groups, *pending_groups]
            auto_report["groupCount"] = len(auto_report["groups"])
        auto_report["appliedGroupCount"] = sum(
            group.get("applied") is True for group in auto_report["groups"]
        )
        auto_report["pendingGroupCount"] = (
            auto_report["groupCount"] - auto_report["appliedGroupCount"]
        )
        write_report(auto_path, auto_report)
        write_report(review_path, review_report)
        print(f"auto_merge={auto_report['groupCount']} -> {auto_path}")
        print(f"needs_review={review_report['groupCount']} -> {review_path}")


if __name__ == "__main__":
    main()
