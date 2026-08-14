from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
import json
from typing import Any

from app.modules.place_checker.contract import AdmResolution, AdmResolutionStatus
from app.modules.place_checker.adapters.postgres_catalog_mapping import (
    PostgresCatalogMappingMixin,
)
from app.modules.place_checker.adapters.postgres_search_query import PLACE_SEARCH_SQL
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.shared.tools.search_places import AdministrativeArea, PlaceProviderCandidate
from app.shared.tools.search_places.normalization import normalize_text


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


class PostgresPlaceCatalog(PostgresCatalogMappingMixin):
    """Read-only PlaceChecker adapter over the normalized Knowledge Graph."""

    provider_name = "knowledge_graph"

    def __init__(self, database_url: str, *, command_timeout: float = 15.0) -> None:
        self.database_url = _asyncpg_url(database_url)
        self.command_timeout = command_timeout
        self._pool = None
        self._pool_lock = asyncio.Lock()

    async def _get_pool(self):
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    import asyncpg

                    self._pool = await asyncpg.create_pool(
                        self.database_url,
                        min_size=1,
                        max_size=4,
                        command_timeout=self.command_timeout,
                    )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def resolve(self, input_name: str) -> AdmResolution:
        normalized = normalize_text(input_name)
        pool = await self._get_pool()
        rows = await pool.fetch(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   GREATEST(
                       similarity(e.normalized_name, $1),
                       similarity(replace(e.normalized_name, ' ', ''), replace($1, ' ', '')),
                       COALESCE(max(similarity(a.normalized_alias, $1)), 0)
                   ) AS score
            FROM knowledge_entities e
            LEFT JOIN knowledge_aliases a ON a.entity_id = e.id
            WHERE e.entity_type IN ('ADM0', 'ADM1', 'ADM2')
              AND (
                  e.normalized_name % $1
                  OR replace(e.normalized_name, ' ', '') = replace($1, ' ', '')
                  OR a.normalized_alias % $1
              )
            GROUP BY e.id
            ORDER BY score DESC, e.canonical_name
            LIMIT 5
            """,
            normalized,
        )
        if not rows or float(rows[0]["score"]) < 0.45:
            return AdmResolution(
                input_name=input_name,
                status=AdmResolutionStatus.unresolved,
            )
        top = rows[0]
        alternatives = [row["canonical_name"] for row in rows[1:]]
        if len(rows) > 1 and float(top["score"]) - float(rows[1]["score"]) < 0.08:
            return AdmResolution(
                input_name=input_name,
                status=AdmResolutionStatus.ambiguous,
                alternatives=[top["canonical_name"], *alternatives],
            )
        level = top["entity_type"].casefold()
        return AdmResolution(
            input_name=input_name,
            status=AdmResolutionStatus.resolved,
            adm_id=top["id"],
            canonical_name=top["canonical_name"],
            country_code="VN",
            region_key=f"vn,{level},{normalize_text(top['canonical_name']).replace(' ', '_')}",
            alternatives=alternatives,
        )

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
        anchor_place_id: str | None = None,
    ) -> list[PlaceProviderCandidate]:
        normalized = [normalize_text(name) for name in lookup_names if normalize_text(name)]
        query = normalized[0] if normalized else ""
        requested_types = self._types_for_hint(place_type_hint)
        # PostgreSQL performs indexed candidate generation; SearchPlacesTool
        # applies the final multi-signal score to this bounded top-K window.
        fetch_limit = min(60, max(1, limit))
        similarity_threshold = 0.22 if anchor_place_id else 0.30
        pool = await self._get_pool()
        rows = await pool.fetch(
            PLACE_SEARCH_SQL,
            query,
            input_adm.adm_id,
            sorted(requested_types),
            fetch_limit,
            anchor_place_id,
            similarity_threshold,
        )
        candidates = [self._candidate(row, input_adm) for row in rows]
        if self._is_generic_travel_discovery(query):
            candidates = [
                candidate
                for candidate in candidates
                if candidate.canonical_type != "travel_place"
                or self._has_tourism_experience(candidate.tags)
                or any(
                    relationship.get("relationshipType") == "Special_Experience"
                    for relationship in candidate.relationship_evidence
                )
            ]
            candidates = self._cap_tourism_experience_groups(
                candidates,
                per_group=max(2, min(12, limit // 3)),
            )
        return candidates

    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]:
        if not place_ids:
            return {}
        pool = await self._get_pool()
        entity_rows = await pool.fetch(
            "SELECT id, entity_type FROM knowledge_entities WHERE id = ANY($1::text[])",
            place_ids,
        )
        property_rows = await pool.fetch(
            """
            SELECT entity_id, key, value, source, updated_at
            FROM knowledge_properties
            WHERE entity_id = ANY($1::text[])
            """,
            place_ids,
        )
        relationship_rows = await pool.fetch(
            """
            SELECT relation.*, owner.entity_id,
                   related.id AS related_entity_id,
                   related.canonical_name AS related_name,
                   owner.direction, owner.scope
            FROM knowledge_relationships relation
            JOIN LATERAL (
                SELECT relation.from_entity_id AS entity_id,
                       CASE WHEN relation.relationship_type IN (
                           'Special_Near', 'Near', 'Must_Visit'
                       ) THEN 'place_to_place' ELSE 'place_to_attribute' END AS direction,
                       CASE WHEN relation.relationship_type IN (
                           'Special_Near', 'Near', 'Must_Visit'
                       ) THEN 'anchor' ELSE 'place' END AS scope
                WHERE relation.from_entity_id = ANY($1::text[])
                UNION ALL
                SELECT relation.to_entity_id,
                       CASE WHEN relation.relationship_type = 'Special_Experience'
                            THEN 'area_to_place' ELSE 'place_to_place' END,
                       CASE WHEN relation.relationship_type = 'Special_Experience'
                            THEN 'destination' ELSE 'anchor' END
                WHERE relation.to_entity_id = ANY($1::text[])
                  AND relation.relationship_type IN (
                      'Special_Experience', 'Special_Near', 'Near', 'Must_Visit'
                  )
            ) owner ON true
            JOIN knowledge_entities related ON related.id = CASE
                WHEN owner.entity_id = relation.from_entity_id
                THEN relation.to_entity_id ELSE relation.from_entity_id END
            WHERE relation.relationship_type IN (
                'Special_Experience', 'Special_Near', 'Near', 'Must_Visit',
                'Offer_Item', 'Has_Style'
            )
            """,
            place_ids,
        )
        style_ids = list(
            dict.fromkeys(
                row["to_entity_id"]
                for row in relationship_rows
                if row["relationship_type"] == "Has_Style"
            )
        )
        style_property_rows = (
            await pool.fetch(
                """
                SELECT entity_id, key, value
                FROM knowledge_properties
                WHERE entity_id = ANY($1::text[])
                  AND key IN ('time_duration', 'time_windows')
                """,
                style_ids,
            )
            if style_ids
            else []
        )
        properties: dict[str, dict[str, Any]] = defaultdict(dict)
        fetched_at: dict[str, datetime] = {}
        for row in property_rows:
            properties[row["entity_id"]][row["key"]] = row["value"]
            current = fetched_at.get(row["entity_id"])
            if current is None or row["updated_at"] > current:
                fetched_at[row["entity_id"]] = row["updated_at"]
        tags: dict[str, list[str]] = defaultdict(list)
        relationships = defaultdict(list)
        style_properties: dict[str, dict[str, Any]] = defaultdict(dict)
        for row in style_property_rows:
            style_properties[row["entity_id"]][row["key"]] = row["value"]
        for row in relationship_rows:
            relationship = self._relationships(
                [
                    self._metadata_relationship(
                        row,
                        style_properties=style_properties.get(row["to_entity_id"]),
                    )
                ]
            )[0]
            relationships[row["entity_id"]].append(relationship)
            if row["relationship_type"] == "Special_Experience":
                tags[row["entity_id"]].append("experience:special_experience")
            elif row["relationship_type"] == "Offer_Item":
                tags[row["entity_id"]].append(f"item:{row['related_name']}")
            elif row["relationship_type"] == "Has_Style":
                tags[row["entity_id"]].append(f"style:{row['related_name']}")
            elif row["relationship_type"] in {"Special_Near", "Near", "Must_Visit"}:
                tags[row["entity_id"]].append(
                    f"relation:{row['relationship_type'].casefold()}"
                )
        return {
            row["id"]: self._metadata(
                row["id"],
                row["entity_type"],
                properties[row["id"]],
                tags[row["id"]],
                fetched_at.get(row["id"]),
                relationships[row["id"]],
            )
            for row in entity_rows
        }

    @staticmethod
    def _metadata_relationship(row, *, style_properties=None):
        raw = row["recommendations"]
        try:
            recommendations = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            recommendations = {}
        payload = recommendations if isinstance(recommendations, dict) else {}
        evidence = recommendations if isinstance(recommendations, list) else []
        confidences = [
            item.get("confidence")
            for item in evidence
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
        ]
        relationship_type = row["relationship_type"]
        distance = payload.get("distance_km")
        threshold = payload.get("threshold_km")
        if relationship_type == "Special_Near":
            ratio = distance / threshold if distance is not None and threshold else 1
            score = max(0.65, 0.95 - 0.30 * ratio)
        elif relationship_type == "Near":
            score = 0.85
        elif relationship_type == "Must_Visit":
            score = 0.95
        elif relationship_type == "Special_Experience":
            score = 0.55 if payload.get("status") == "pending" else 0.78
        elif relationship_type == "Offer_Item":
            score = max(confidences, default=0.45 if payload.get("status") == "pending" else 0.72)
        else:
            score = min(0.75, 0.45 + float(payload.get("priority", 40)) / 400)
        relationship_properties = dict(style_properties or {})
        relationship_properties.update(payload.get("properties") or {})
        return {
            "relationshipType": relationship_type,
            "direction": row["direction"],
            "scope": row["scope"],
            "fromEntityId": row["from_entity_id"],
            "toEntityId": row["to_entity_id"],
            "relatedEntityId": row["related_entity_id"],
            "relatedName": row["related_name"],
            "status": payload.get("status"),
            "confidence": max(confidences) if confidences else None,
            "priority": payload.get("priority"),
            "distanceKm": distance,
            "thresholdKm": threshold,
            "source": row["source"],
            "sourceNote": row["source_note"],
            "properties": relationship_properties,
            "score": min(1, max(0, score)),
        }
