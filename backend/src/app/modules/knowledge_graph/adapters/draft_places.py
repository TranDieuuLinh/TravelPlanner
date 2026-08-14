from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime

from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceProviderCandidate,
)
from app.shared.tools.search_places.normalization import normalize_text


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


class PostgresDraftPlaceStore:
    """Conservatively stages external place records in the live Knowledge Graph."""

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
                        max_size=2,
                        command_timeout=self.command_timeout,
                    )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def upsert_draft(
        self,
        candidate: PlaceProviderCandidate,
        *,
        input_adm: AdministrativeArea,
    ) -> PlaceProviderCandidate:
        if not candidate.provider_id or not candidate.source_url:
            return candidate
        pool = await self._get_pool()
        async with pool.acquire() as connection, connection.transaction():
            existing = await self._find_existing(connection, candidate, input_adm)
            entity_id = existing["id"] if existing else self._entity_id(candidate)
            existing_status = existing["status"] if existing else "pending"
            if existing_status == "rejected":
                return candidate
            await connection.execute(
                """INSERT INTO knowledge_entities
                       (id, canonical_name, normalized_name, entity_type, status, review_count)
                   VALUES ($1,$2,$3,$4,'pending',$5)
                   ON CONFLICT (id) DO UPDATE SET
                       canonical_name = CASE
                           WHEN knowledge_entities.status = 'verified'
                           THEN knowledge_entities.canonical_name ELSE EXCLUDED.canonical_name END,
                       normalized_name = CASE
                           WHEN knowledge_entities.status = 'verified'
                           THEN knowledge_entities.normalized_name ELSE EXCLUDED.normalized_name END,
                       review_count = CASE
                           WHEN knowledge_entities.status = 'verified'
                           THEN knowledge_entities.review_count ELSE EXCLUDED.review_count END,
                       updated_at = now()""",
                entity_id,
                candidate.name,
                normalize_text(candidate.name),
                self._entity_type(candidate.canonical_type),
                candidate.review_count,
            )
            status = await connection.fetchval(
                "SELECT status FROM knowledge_entities WHERE id=$1", entity_id
            )
            for key, value in self._properties(candidate).items():
                await self._upsert_property(
                    connection,
                    entity_id=entity_id,
                    key=key,
                    value=value,
                    source=candidate.source_url,
                    fetched_at=candidate.fetched_at or datetime.now(UTC),
                )
            await connection.execute(
                """INSERT INTO knowledge_relationships
                       (from_entity_id, relationship_type, to_entity_id,
                        recommendations, source, source_note)
                   SELECT $1, 'Located_In', area.id,
                          '{"status":"pending"}'::jsonb, $3, $4
                   FROM knowledge_entities area WHERE area.id=$2
                   ON CONFLICT (from_entity_id, relationship_type, to_entity_id)
                   DO NOTHING""",
                entity_id,
                input_adm.adm_id,
                candidate.source_url,
                "provider=google_maps_playwright;verification=not_verified",
            )
        return candidate.model_copy(
            update={
                "entity_id": entity_id,
                "verification_status": (
                    "verified" if status == "verified" else "not_verified"
                ),
            }
        )

    @staticmethod
    async def _find_existing(connection, candidate, input_adm):
        return await connection.fetchrow(
            """SELECT entity.id, entity.status
               FROM knowledge_entities entity
               WHERE entity.status <> 'rejected'
                 AND (
                     EXISTS (
                         SELECT 1 FROM knowledge_properties property
                         WHERE property.entity_id=entity.id
                           AND property.key='google_place_id' AND property.value=$1
                     )
                     OR EXISTS (
                         SELECT 1 FROM knowledge_properties property
                         WHERE property.entity_id=entity.id
                           AND property.key='url_google_map' AND property.value=$2
                     )
                     OR (
                         entity.normalized_name=$3
                         AND EXISTS (
                             SELECT 1 FROM knowledge_relationships location
                             WHERE location.from_entity_id=entity.id
                               AND location.relationship_type='Located_In'
                               AND location.to_entity_id=$4
                         )
                     )
                 )
               ORDER BY CASE entity.status WHEN 'verified' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
               LIMIT 1""",
            candidate.provider_id,
            candidate.source_url,
            normalize_text(candidate.name),
            input_adm.adm_id,
        )

    @staticmethod
    async def _upsert_property(
        connection,
        *,
        entity_id: str,
        key: str,
        value: str,
        source: str,
        fetched_at: datetime,
    ) -> None:
        await connection.execute(
            """INSERT INTO knowledge_properties
                   (entity_id, key, value, source, note, fetch_at)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (entity_id, key) DO UPDATE SET
                   value=EXCLUDED.value, source=EXCLUDED.source,
                   note=EXCLUDED.note, fetch_at=EXCLUDED.fetch_at,
                   updated_at=now()
               WHERE knowledge_properties.source LIKE '%google.com/maps%'
                  OR knowledge_properties.note LIKE 'provider=google_maps_playwright;%'
                  OR btrim(knowledge_properties.value)=''""",
            entity_id,
            key,
            value,
            source,
            "provider=google_maps_playwright;verification=not_verified",
            fetched_at,
        )

    @staticmethod
    def _properties(candidate: PlaceProviderCandidate) -> dict[str, str]:
        metadata = candidate.provider_metadata
        values: dict[str, object] = {
            "google_place_id": candidate.provider_id,
            "url_google_map": candidate.source_url,
            "latitude": candidate.coordinates.latitude if candidate.coordinates else None,
            "longitude": candidate.coordinates.longitude if candidate.coordinates else None,
            "address": candidate.address,
            "rating": candidate.rating,
            "review_count": candidate.review_count,
            "tags": candidate.tags or None,
            "description": metadata.get("description"),
            "phone": metadata.get("phone"),
            "website": metadata.get("website"),
            "image": metadata.get("image"),
            "meta_json": {
                "google": {
                    key: value
                    for key, value in metadata.items()
                    if key not in {"phone", "website", "image"}
                }
            },
        }
        return {
            key: json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value)
            for key, value in values.items()
            if value not in (None, "", [], {})
        }

    @staticmethod
    def _entity_id(candidate: PlaceProviderCandidate) -> str:
        digest = hashlib.sha256(
            f"{candidate.provider}:{candidate.provider_id}".encode()
        ).hexdigest()[:24]
        return f"google_maps:{digest}"

    @staticmethod
    def _entity_type(canonical_type: str | None) -> str:
        return {
            "restaurant": "Restaurant",
            "drink_dessert": "DrinkDessert",
            "accommodation": "Accommodation",
        }.get(canonical_type or "", "TravelPlace")
