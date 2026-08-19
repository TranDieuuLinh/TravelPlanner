from __future__ import annotations

import json


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


class AutoAttachStoreMixin:
    """Persistence methods for the Knowledge Graph auto-attach catalog."""

    async def list_auto_attach_rules(self) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT rule_id, name, style_group, entity_types, keywords,
                          exact_names, exclude_keywords, time_duration,
                          time_windows, override_count, status, source
                   FROM knowledge_auto_attach_rules
                   ORDER BY name, rule_id"""
            )
        return [dict(row) | {"time_windows": _json_value(row["time_windows"])} for row in rows]

    async def upsert_auto_attach_rule(self, **payload) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO knowledge_auto_attach_rules
                   (rule_id, name, style_group, entity_types, keywords,
                    exact_names, exclude_keywords, time_duration, time_windows,
                    override_count, status, source)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12)
                   ON CONFLICT (rule_id) DO UPDATE SET
                    name=EXCLUDED.name, style_group=EXCLUDED.style_group,
                    entity_types=EXCLUDED.entity_types, keywords=EXCLUDED.keywords,
                    exact_names=EXCLUDED.exact_names,
                    exclude_keywords=EXCLUDED.exclude_keywords,
                    time_duration=EXCLUDED.time_duration,
                    time_windows=EXCLUDED.time_windows,
                    override_count=EXCLUDED.override_count,
                    status=EXCLUDED.status, source=EXCLUDED.source, updated_at=now()
                   RETURNING rule_id, name, style_group, entity_types, keywords,
                             exact_names, exclude_keywords, time_duration,
                             time_windows, override_count, status, source""",
                payload["rule_id"], payload["name"], payload["style_group"],
                payload["entity_types"], payload["keywords"], payload["exact_names"],
                payload["exclude_keywords"], payload["time_duration"],
                json.dumps(payload["time_windows"]), payload["override_count"],
                payload["status"], payload["source"],
            )
        result = dict(row)
        result["time_windows"] = _json_value(result["time_windows"])
        return result

    async def delete_auto_attach_rule(self, rule_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM knowledge_auto_attach_rules WHERE rule_id=$1", rule_id
            )
        return result.endswith("1")

    async def list_auto_attach_aliases(self) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT keyword, aliases, source FROM knowledge_auto_attach_aliases ORDER BY keyword"
            )
        return [dict(row) for row in rows]

    async def upsert_auto_attach_alias(self, **payload) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO knowledge_auto_attach_aliases(keyword, aliases, source)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (keyword) DO UPDATE SET aliases=EXCLUDED.aliases,
                       source=EXCLUDED.source, updated_at=now()
                   RETURNING keyword, aliases, source""",
                payload["keyword"], payload["aliases"], payload["source"],
            )
        return dict(row)

    async def list_auto_attach_aliases(self) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT keyword, aliases, source FROM knowledge_auto_attach_aliases ORDER BY keyword"
            )
        return [dict(row) for row in rows]

    async def upsert_auto_attach_alias(self, **payload) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO knowledge_auto_attach_aliases(keyword, aliases, source)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (keyword) DO UPDATE SET aliases=EXCLUDED.aliases,
                       source=EXCLUDED.source, updated_at=now()
                   RETURNING keyword, aliases, source""",
                payload["keyword"], payload["aliases"], payload["source"],
            )
        return dict(row)
