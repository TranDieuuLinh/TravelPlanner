from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
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
        tag_rows = await pool.fetch(
            """
            SELECT r.from_entity_id AS entity_id, r.relationship_type,
                   target.canonical_name
            FROM knowledge_relationships r
            JOIN knowledge_entities target ON target.id = r.to_entity_id
            WHERE r.from_entity_id = ANY($1::text[])
              AND r.relationship_type IN ('Special_Experience', 'Offer_Item')
            """,
            place_ids,
        )
        properties: dict[str, dict[str, Any]] = defaultdict(dict)
        fetched_at: dict[str, datetime] = {}
        for row in property_rows:
            properties[row["entity_id"]][row["key"]] = row["value"]
            current = fetched_at.get(row["entity_id"])
            if current is None or row["updated_at"] > current:
                fetched_at[row["entity_id"]] = row["updated_at"]
        tags: dict[str, list[str]] = defaultdict(list)
        for row in tag_rows:
            prefix = "experience" if row["relationship_type"] == "Special_Experience" else "item"
            tags[row["entity_id"]].append(f"{prefix}:{row['canonical_name']}")
        return {
            row["id"]: self._metadata(
                row["id"],
                row["entity_type"],
                properties[row["id"]],
                tags[row["id"]],
                fetched_at.get(row["id"]),
            )
            for row in entity_rows
        }
