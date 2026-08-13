from __future__ import annotations

import json

from app.modules.knowledge_graph.adapters.auto_attach import AutoAttachStoreMixin


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


class PostgresKnowledgeGraphStore(AutoAttachStoreMixin):
    """Owns the knowledge_* tables used by the admin graph UI."""

    def __init__(self, database_url: str, *, command_timeout: float = 15.0) -> None:
        self.database_url = _asyncpg_url(database_url)
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg  # type: ignore[import-untyped]
            except ImportError as exc:
                raise RuntimeError("asyncpg is required for Knowledge Graph") from exc
            self._pool = await asyncpg.create_pool(
                self.database_url,
                command_timeout=self.command_timeout,
                min_size=1,
                max_size=10,
            )
        return self._pool

    async def stats(self) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT
                    (SELECT count(*) FROM knowledge_entities) AS entity_count,
                    (SELECT count(*) FROM knowledge_aliases) AS alias_count,
                    (SELECT count(*) FROM knowledge_relationships) AS relationship_count"""
            )
        return dict(row)

    async def search_stats(self, query: str) -> dict:
        pool = await self._get_pool()
        pattern = f"%{query}%"
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT
                    (SELECT count(*) FROM knowledge_entities
                     WHERE canonical_name ILIKE $1 OR id ILIKE $1) AS entity_count,
                    (SELECT count(*) FROM knowledge_aliases
                     WHERE alias ILIKE $1 OR normalized_alias ILIKE $1) AS alias_count,
                    (SELECT count(*) FROM knowledge_properties
                     WHERE key ILIKE $1 OR value ILIKE $1 OR source ILIKE $1) AS property_count,
                    (SELECT count(*) FROM knowledge_relationships
                     WHERE relationship_type ILIKE $1 OR from_entity_id ILIKE $1
                        OR to_entity_id ILIKE $1 OR source ILIKE $1) AS relationship_count""",
                pattern,
            )
        result = dict(row)
        result["query"] = query
        result["total_count"] = sum(
            result[key]
            for key in ("entity_count", "alias_count", "property_count", "relationship_count")
        )
        return result

    async def list_entities(self, **filters) -> tuple[list[dict], int]:
        limit = filters["limit"]
        offset = filters["offset"]
        values: list[object] = []
        clauses: list[str] = []

        def add_clause(sql: str, value: object) -> None:
            values.append(value)
            clauses.append(sql.replace("$VALUE", f"${len(values)}"))

        search_terms = [
            item.strip()
            for item in (filters.get("search") or "").split(",")
            if item.strip()
        ]
        if search_terms:
            search_patterns = [f"%{item}%" for item in search_terms]
            add_clause(
                "(canonical_name ILIKE ANY($VALUE::text[]) OR id ILIKE ANY($VALUE::text[]))",
                search_patterns,
            )
        if filters.get("entity_type"):
            add_clause("entity_type = $VALUE", filters["entity_type"])
        if filters.get("status"):
            add_clause("status = $VALUE", filters["status"])
        excluded = [
            f"%{item.strip().lower()}%"
            for item in (filters.get("exclude_names") or "").split(",")
            if item.strip()
        ]
        if excluded:
            add_clause("NOT (lower(canonical_name) LIKE ANY($VALUE::text[]))", excluded)
        missing_properties = [
            item.strip()
            for item in (filters.get("missing_properties") or "").split(",")
            if item.strip()
        ]
        if missing_properties:
            add_clause(
                "(SELECT count(DISTINCT key) FROM knowledge_properties "
                "WHERE entity_id=knowledge_entities.id AND key = ANY($VALUE::text[])) "
                "< cardinality($VALUE::text[])",
                missing_properties,
            )

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sort = {"name": "canonical_name", "id": "id", "type": "entity_type", "status": "status"}.get(
            filters.get("sort_by"), "canonical_name"
        )
        direction = "DESC" if filters.get("sort_direction") == "desc" else "ASC"
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            count_row = await connection.fetchrow(f"SELECT count(*) AS total FROM knowledge_entities {where}", *values)
            rows = await connection.fetch(
                f"""SELECT id, canonical_name, entity_type, status, review_count, created_at, updated_at
                    FROM knowledge_entities {where}
                    ORDER BY {sort} {direction}, id ASC LIMIT ${len(values) + 1} OFFSET ${len(values) + 2}""",
                *values, limit, offset,
            )
        return [dict(row) for row in rows], int(count_row["total"])

    async def entity_filter_options(self) -> dict[str, list[str]]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            entity_types = await connection.fetch(
                "SELECT DISTINCT entity_type FROM knowledge_entities ORDER BY entity_type"
            )
            statuses = await connection.fetch(
                "SELECT DISTINCT status FROM knowledge_entities ORDER BY status"
            )
            property_keys = await connection.fetch(
                "SELECT DISTINCT key FROM knowledge_properties "
                "WHERE key IS NOT NULL ORDER BY key"
            )
            relationship_types = await connection.fetch(
                "SELECT DISTINCT relationship_type FROM knowledge_relationships "
                "WHERE relationship_type IS NOT NULL ORDER BY relationship_type"
            )
        return {
            "entity_types": [row["entity_type"] for row in entity_types],
            "statuses": [row["status"] for row in statuses],
            "property_keys": [row["key"] for row in property_keys],
            "relationship_types": [row["relationship_type"] for row in relationship_types],
        }

    async def list_relationships(self, **filters) -> tuple[list[dict], int]:
        limit, offset = filters["limit"], filters["offset"]
        values: list[object] = []
        clauses: list[str] = []

        def add(sql: str, value: object) -> None:
            values.append(value)
            clauses.append(sql.replace("$VALUE", f"${len(values)}"))

        if filters.get("relationship"):
            add("r.relationship_type = $VALUE", filters["relationship"])
        if filters.get("from_entity_id"):
            add("r.from_entity_id = $VALUE", filters["from_entity_id"])
        if filters.get("to_entity_id"):
            add("r.to_entity_id = $VALUE", filters["to_entity_id"])
        if filters.get("search"):
            add("(r.from_entity_id ILIKE '%' || $VALUE || '%' OR r.to_entity_id ILIKE '%' || $VALUE || '%')", filters["search"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            count = await connection.fetchval(f"SELECT count(*) FROM knowledge_relationships r {where}", *values)
            rows = await connection.fetch(
                f"""SELECT r.id, r.from_entity_id, r.relationship_type AS relationship, r.to_entity_id, r.source, r.created_at
                    FROM knowledge_relationships r {where}
                    ORDER BY r.id {'DESC' if filters.get('sort_direction') == 'desc' else 'ASC'}
                    LIMIT ${len(values) + 1} OFFSET ${len(values) + 2}""",
                *values, limit, offset,
            )
        return [dict(row) for row in rows], int(count)

    async def get_entity(self, entity_id: str, **limits) -> dict | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            entity = await connection.fetchrow("SELECT * FROM knowledge_entities WHERE id=$1", entity_id)
            if not entity:
                return None
            alias_offset, alias_limit = limits.get("alias_offset", 0), limits.get("alias_limit", 100)
            prop_offset, prop_limit = limits.get("property_offset", 0), limits.get("property_limit", 100)
            rel_offset, rel_limit = limits.get("relationship_offset", 0), limits.get("relationship_limit", 100)
            aliases = await connection.fetch("""SELECT id, alias, language, created_at FROM knowledge_aliases
                WHERE entity_id=$1 ORDER BY id LIMIT $2 OFFSET $3""", entity_id, alias_limit, alias_offset)
            properties = await connection.fetch("""SELECT id, key, value, source, updated_at FROM knowledge_properties
                WHERE entity_id=$1 ORDER BY id LIMIT $2 OFFSET $3""", entity_id, prop_limit, prop_offset)
            relationships = await connection.fetch("""WITH directed AS (
                    SELECT id, from_entity_id, relationship_type AS relationship, to_entity_id, source, created_at,
                        CASE WHEN from_entity_id=$1 THEN 0 ELSE 1 END AS direction_order,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN from_entity_id=$1 THEN 0 ELSE 1 END
                            ORDER BY id
                        ) AS direction_rank
                    FROM knowledge_relationships
                    WHERE from_entity_id=$1 OR to_entity_id=$1
                )
                SELECT id, from_entity_id, relationship, to_entity_id, source, created_at
                FROM directed
                ORDER BY direction_rank, direction_order, id DESC
                LIMIT $2 OFFSET $3""", entity_id, rel_limit, rel_offset)
            alias_total = await connection.fetchval("SELECT count(*) FROM knowledge_aliases WHERE entity_id=$1", entity_id)
            prop_total = await connection.fetchval("SELECT count(*) FROM knowledge_properties WHERE entity_id=$1", entity_id)
            rel_total = await connection.fetchval("SELECT count(*) FROM knowledge_relationships WHERE from_entity_id=$1 OR to_entity_id=$1", entity_id)
        result = dict(entity)
        result.update(
            aliases=[dict(row) for row in aliases], properties=[dict(row) for row in properties],
            relationships=[dict(row) for row in relationships], alias_total=int(alias_total),
            property_total=int(prop_total), relationship_total=int(rel_total),
            alias_has_more=alias_offset + len(aliases) < alias_total,
            property_has_more=prop_offset + len(properties) < prop_total,
            relationship_has_more=rel_offset + len(relationships) < rel_total,
        )
        return result

    async def create_entity(self, **payload) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute("""INSERT INTO knowledge_entities
                (id, canonical_name, normalized_name, entity_type, status)
                VALUES ($1,$2,$3,$4,$5)""", payload["entity_id"], payload["canonical_name"], payload["canonical_name"].strip().lower(), payload["entity_type"], payload["status"])
        return await self.get_entity(payload["entity_id"])

    async def update_entity(self, entity_id: str, **payload) -> dict | None:
        updates = {key: value for key, value in payload.items() if value is not None}
        new_entity_id = updates.pop("entity_id", None)
        if new_entity_id == entity_id:
            new_entity_id = None
        if not updates and new_entity_id is None:
            return await self.get_entity(entity_id)
        if "canonical_name" in updates:
            updates["normalized_name"] = updates["canonical_name"].strip().lower()
        pool = await self._get_pool()
        async with pool.acquire() as connection, connection.transaction():
            if new_entity_id is not None:
                duplicate = await connection.fetchval(
                    "SELECT 1 FROM knowledge_entities WHERE id=$1",
                    new_entity_id,
                )
                if duplicate:
                    raise ValueError("entity id already exists")
                source = await connection.fetchrow(
                    """SELECT canonical_name, normalized_name, entity_type, status, review_count
                       FROM knowledge_entities WHERE id=$1""",
                    entity_id,
                )
                if not source:
                    return None
                await connection.execute(
                    """INSERT INTO knowledge_entities
                       (id, canonical_name, normalized_name, entity_type, status, review_count)
                       VALUES ($1,$2,$3,$4,$5,$6)""",
                    new_entity_id,
                    updates.get("canonical_name", source["canonical_name"]),
                    updates.get("normalized_name", source["normalized_name"]),
                    updates.get("entity_type", source["entity_type"]),
                    updates.get("status", source["status"]),
                    source["review_count"],
                )
                await connection.execute(
                    "UPDATE knowledge_aliases SET entity_id=$2 WHERE entity_id=$1",
                    entity_id,
                    new_entity_id,
                )
                await connection.execute(
                    "UPDATE knowledge_properties SET entity_id=$2 WHERE entity_id=$1",
                    entity_id,
                    new_entity_id,
                )
                await connection.execute(
                    "UPDATE knowledge_relationships SET from_entity_id=$2 WHERE from_entity_id=$1",
                    entity_id,
                    new_entity_id,
                )
                await connection.execute(
                    "UPDATE knowledge_relationships SET to_entity_id=$2 WHERE to_entity_id=$1",
                    entity_id,
                    new_entity_id,
                )
                await connection.execute("DELETE FROM knowledge_entities WHERE id=$1", entity_id)
            else:
                assignments = []
                values: list[object] = [entity_id]
                for key, value in updates.items():
                    values.append(value)
                    assignments.append(f"{key}=${len(values)}")
                await connection.execute(
                    f"UPDATE knowledge_entities SET {', '.join(assignments)}, updated_at=now() WHERE id=$1",
                    *values,
                )
        return await self.get_entity(new_entity_id or entity_id)

    async def delete_entity(self, entity_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute("DELETE FROM knowledge_entities WHERE id=$1", entity_id)
        return result.endswith("1")

    async def copy_entity(self, source_id: str, new_id: str, new_name: str) -> dict | None:
        source = await self.get_entity(source_id)
        if not source:
            return None
        pool = await self._get_pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute("""INSERT INTO knowledge_entities(id, canonical_name, normalized_name, entity_type, status)
                VALUES($1,$2,$3,$4,$5)""", new_id, new_name, new_name.strip().lower(), source["entity_type"], source["status"])
            for alias in source["aliases"]:
                await connection.execute("INSERT INTO knowledge_aliases(entity_id, alias, normalized_alias, language) VALUES($1,$2,$3,$4)", new_id, alias["alias"], alias["alias"].lower(), alias["language"])
            for prop in source["properties"]:
                await connection.execute("INSERT INTO knowledge_properties(entity_id, key, value, source) VALUES($1,$2,$3,$4)", new_id, prop["key"], prop["value"], prop["source"])
        return await self.get_entity(new_id)

    async def add_alias(self, entity_id: str, alias: str, language: str) -> dict | None:
        return await self._mutate_detail("INSERT INTO knowledge_aliases(entity_id, alias, normalized_alias, language) VALUES($1,$2,$3,$4)", entity_id, alias, alias.strip().lower(), language)

    async def update_alias(self, entity_id: str, alias_id: int, alias: str, language: str) -> dict | None:
        return await self._mutate_detail("UPDATE knowledge_aliases SET alias=$2, normalized_alias=$3, language=$4 WHERE entity_id=$1 AND id=$5", entity_id, alias, alias.strip().lower(), language, alias_id)

    async def delete_alias(self, entity_id: str, alias_id: int) -> bool:
        return await self._delete_child("knowledge_aliases", entity_id, alias_id)

    async def add_property(self, entity_id: str, key: str, value: str, source: str | None) -> dict | None:
        return await self._mutate_detail("INSERT INTO knowledge_properties(entity_id, key, value, source) VALUES($1,$2,$3,$4)", entity_id, key, value, source)

    async def update_property(self, entity_id: str, prop_id: int, key: str, value: str, source: str | None) -> dict | None:
        return await self._mutate_detail("UPDATE knowledge_properties SET key=$2, value=$3, source=$4, updated_at=now() WHERE entity_id=$1 AND id=$5", entity_id, key, value, source, prop_id)

    async def delete_property(self, entity_id: str, prop_id: int) -> bool:
        return await self._delete_child("knowledge_properties", entity_id, prop_id)

    async def add_relationship(self, entity_id: str, relationship: str, to_entity_id: str, source: str | None, recommendations: dict | list[dict] | None) -> dict | None:
        return await self._mutate_detail("INSERT INTO knowledge_relationships(from_entity_id, relationship_type, to_entity_id, source, recommendations) VALUES($1,$2,$3,$4,$5::jsonb)", entity_id, relationship, to_entity_id, source, json.dumps(recommendations or {}))

    async def update_relationship(
        self,
        entity_id: str,
        rel_id: int,
        relationship: str,
        to_entity_id: str,
        source: str | None,
        recommendations: dict | list[dict] | None,
        *,
        from_entity_id: str | None = None,
    ) -> dict | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(
                """UPDATE knowledge_relationships
                   SET from_entity_id=COALESCE($2, from_entity_id), relationship_type=$3,
                       to_entity_id=$4, source=$5, recommendations=$6::jsonb, updated_at=now()
                   WHERE id=$7 AND (from_entity_id=$1 OR to_entity_id=$1)""",
                entity_id,
                from_entity_id,
                relationship,
                to_entity_id,
                source,
                json.dumps(recommendations or {}),
                rel_id,
            )
        if not result.endswith("1"):
            return None
        return await self.get_entity(entity_id)

    async def delete_relationship(self, entity_id: str, rel_id: int) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM knowledge_relationships WHERE id=$1 AND (from_entity_id=$2 OR to_entity_id=$2)",
                rel_id,
                entity_id,
            )
        return result.endswith("1")

    async def count_low_review(self, threshold: int) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            value = await connection.fetchval(
                "SELECT count(*) FROM knowledge_entities WHERE review_count IS NOT NULL AND review_count < $1",
                threshold,
            )
        return int(value)

    async def delete_low_review(self, threshold: int) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM knowledge_entities WHERE review_count IS NOT NULL AND review_count < $1",
                threshold,
            )
        return int(result.split()[-1])

    async def _mutate_detail(self, sql: str, entity_id: str, *args) -> dict | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(sql, entity_id, *args)
        return await self.get_entity(entity_id)

    async def _delete_child(self, table: str, entity_id: str, child_id: int, owner_column: str = "entity_id") -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(f"DELETE FROM {table} WHERE {owner_column}=$1 AND id=$2", entity_id, child_id)
        return result.endswith("1")
