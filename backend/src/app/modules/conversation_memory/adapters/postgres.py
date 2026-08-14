"""PostgreSQL database adapter implementation for Conversation Memory module using asyncpg."""

import json
from typing import Sequence
import asyncpg

from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import (
    MemoryNotFound,
    MemoryPersistenceError,
    MemoryRepository,
    MemoryVersionConflict,
)


class PostgresMemoryRepository(MemoryRepository):
    """PostgreSQL repository using asyncpg for agent_conversation_memory storage."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def load_working_memory(
        self,
        chat_id: str,
        user_id: int,
    ) -> WorkingMemoryState | None:
        async with self.pool.acquire() as conn:
            return await self._load_working_memory_conn(conn, chat_id, user_id)

    async def save_working_memory(
        self,
        memory: WorkingMemoryState,
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await self._save_working_memory_conn(
                    conn, memory, expected_version=expected_version
                )

    async def append_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await self._append_facts_conn(
                    conn, chat_id, user_id, facts, expected_version=expected_version
                )

    # -------------------------------------------------------------------------
    # Internal helpers taking an active connection (preventing nested checkout)
    # -------------------------------------------------------------------------

    async def _load_working_memory_conn(
        self,
        conn: asyncpg.Connection,
        chat_id: str,
        user_id: int,
        for_update: bool = False,
    ) -> WorkingMemoryState | None:
        for_update_clause = " FOR UPDATE" if for_update else ""
        query = f"""
        SELECT
            chat_id, user_id, destination, duration_days, travelers, budget,
            preferences, avoids, mentioned_places, selected_places,
            current_plan_ref, pending_goal, last_route, summary,
            version, updated_at
        FROM agent_conversation_memory
        WHERE chat_id = $1 AND user_id = $2{for_update_clause};
        """
        row = await conn.fetchrow(query, chat_id, user_id)
        if not row:
            return None

        facts_query = """
        SELECT
            fact_id, fact_type, key, value, normalized_value, value_type, scope, status,
            confirmed_by_user, confidence, source_turn, source_excerpt,
            source_message_id, extracted_by, observed_at, expires_at, created_at
        FROM agent_conversation_memory_facts
        WHERE chat_id = $1 AND user_id = $2 AND status = 'active'
        ORDER BY created_at ASC;
        """
        fact_rows = await conn.fetch(facts_query, chat_id, user_id)
        active_facts = [self._row_to_memory_fact(r) for r in fact_rows]
        confirmed_facts = [f for f in active_facts if f.confirmed_by_user]

        return WorkingMemoryState(
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            destination=row["destination"],
            duration_days=row["duration_days"],
            travelers=row["travelers"],
            budget=json.loads(row["budget"]) if row["budget"] else None,
            preferences=json.loads(row["preferences"]) if row["preferences"] else [],
            avoids=json.loads(row["avoids"]) if row["avoids"] else [],
            mentioned_places=json.loads(row["mentioned_places"]) if row["mentioned_places"] else [],
            selected_places=json.loads(row["selected_places"]) if row["selected_places"] else [],
            current_plan_ref=row["current_plan_ref"],
            pending_goal=row["pending_goal"],
            last_route=row["last_route"],
            summary=row["summary"],
            version=row["version"],
            active_facts=active_facts,
            confirmed_facts=confirmed_facts,
            last_updated_at=row["updated_at"],
        )

    async def _save_working_memory_conn(
        self,
        conn: asyncpg.Connection,
        memory: WorkingMemoryState,
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        target_expected = memory.version if expected_version is None else expected_version
        existing = await conn.fetchrow(
            "SELECT version, user_id FROM agent_conversation_memory WHERE chat_id = $1 FOR UPDATE;",
            memory.chat_id,
        )
        if existing:
            if existing["user_id"] != memory.user_id:
                raise MemoryNotFound(
                    f"Chat memory '{memory.chat_id}' not found for user {memory.user_id}."
                )
            current_ver = existing["version"]
            if current_ver != target_expected:
                raise MemoryVersionConflict(
                    f"Version conflict for chat '{memory.chat_id}': expected {target_expected}, found {current_ver}."
                )
            next_ver = current_ver + 1
            update_query = """
            UPDATE agent_conversation_memory
            SET
                destination = $3,
                duration_days = $4,
                travelers = $5,
                budget = $6::jsonb,
                preferences = $7::jsonb,
                avoids = $8::jsonb,
                mentioned_places = $9::jsonb,
                selected_places = $10::jsonb,
                current_plan_ref = $11,
                pending_goal = $12,
                last_route = $13,
                summary = $14,
                version = $15,
                updated_at = now()
            WHERE chat_id = $1 AND user_id = $2
            RETURNING updated_at;
            """
            updated_at = await conn.fetchval(
                update_query,
                memory.chat_id,
                memory.user_id,
                memory.destination,
                memory.duration_days,
                memory.travelers,
                json.dumps(memory.budget),
                json.dumps(memory.preferences),
                json.dumps(memory.avoids),
                json.dumps(memory.mentioned_places),
                json.dumps(memory.selected_places),
                memory.current_plan_ref,
                memory.pending_goal,
                memory.last_route,
                memory.summary,
                next_ver,
            )
        else:
            if target_expected != 0:
                raise MemoryVersionConflict(
                    f"Version conflict for new chat '{memory.chat_id}': expected {target_expected}, found 0."
                )
            next_ver = 1
            insert_query = """
            INSERT INTO agent_conversation_memory (
                chat_id, user_id, destination, duration_days, travelers, budget,
                preferences, avoids, mentioned_places, selected_places,
                current_plan_ref, pending_goal, last_route, summary, version
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11, $12, $13, $14, $15)
            RETURNING updated_at;
            """
            updated_at = await conn.fetchval(
                insert_query,
                memory.chat_id,
                memory.user_id,
                memory.destination,
                memory.duration_days,
                memory.travelers,
                json.dumps(memory.budget),
                json.dumps(memory.preferences),
                json.dumps(memory.avoids),
                json.dumps(memory.mentioned_places),
                json.dumps(memory.selected_places),
                memory.current_plan_ref,
                memory.pending_goal,
                memory.last_route,
                memory.summary,
                next_ver,
            )

        return memory.model_copy(
            update={
                "version": next_ver,
                "last_updated_at": updated_at,
            }
        )

    async def _append_facts_conn(
        self,
        conn: asyncpg.Connection,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        existing_memory = await self._load_working_memory_conn(
            conn, chat_id, user_id, for_update=True
        )
        if existing_memory:
            current_ver = existing_memory.version
            if expected_version is None:
                raise MemoryVersionConflict(
                    f"Version conflict for chat '{chat_id}': expected_version must be explicitly passed for existing chat (current version: {current_ver})."
                )
            if current_ver != expected_version:
                raise MemoryVersionConflict(
                    f"Version conflict for chat '{chat_id}': expected {expected_version}, found {current_ver}."
                )
            target_ver = current_ver
        else:
            check_ver = 0 if expected_version is None else expected_version
            if check_ver != 0:
                raise MemoryVersionConflict(
                    f"Version conflict for new chat '{chat_id}': expected {check_ver}, found 0."
                )
            # Create parent memory row first so composite FK (chat_id, user_id) in agent_conversation_memory_facts passes
            insert_parent_query = """
            INSERT INTO agent_conversation_memory (
                chat_id, user_id, destination, duration_days, travelers, budget,
                preferences, avoids, mentioned_places, selected_places,
                current_plan_ref, pending_goal, last_route, summary, version
            ) VALUES ($1, $2, NULL, NULL, NULL, 'null'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NULL, NULL, NULL, NULL, 0);
            """
            await conn.execute(insert_parent_query, chat_id, user_id)
            target_ver = 0

        # Insert facts into agent_conversation_memory_facts
        for fact in facts:
            norm_val = fact.computed_normalized_value
            existing_facts = await conn.fetch(
                """
                SELECT fact_id, confirmed_by_user, confidence, value
                FROM agent_conversation_memory_facts
                WHERE chat_id = $1 AND key = $2 AND normalized_value = $3 AND status = 'active';
                """,
                chat_id,
                fact.key,
                norm_val,
            )
            should_skip_insert = False
            for ex in existing_facts:
                if ex["confirmed_by_user"] and not fact.confirmed_by_user:
                    should_skip_insert = True
                    break
                await conn.execute(
                    "UPDATE agent_conversation_memory_facts SET status = 'superseded', updated_at = now() WHERE fact_id = $1;",
                    ex["fact_id"],
                )

            if should_skip_insert:
                continue

            await conn.execute(
                """
                INSERT INTO agent_conversation_memory_facts (
                    fact_id, chat_id, user_id, fact_type, key, value, normalized_value, value_type,
                    scope, status, confirmed_by_user, confidence, source_turn,
                    source_excerpt, source_message_id, extracted_by
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16);
                """,
                fact.fact_id,
                chat_id,
                user_id,
                fact.fact_type,
                fact.key,
                json.dumps(fact.value),
                norm_val,
                fact.value_type,
                fact.scope,
                fact.status,
                fact.confirmed_by_user,
                fact.provenance.confidence,
                fact.provenance.source_turn,
                fact.provenance.source_excerpt,
                fact.provenance.source_message_id,
                fact.provenance.extracted_by,
            )

        # Update parent memory version atomically in the same transaction
        next_ver = target_ver + 1
        await conn.execute(
            "UPDATE agent_conversation_memory SET version = $3, updated_at = now() WHERE chat_id = $1 AND user_id = $2;",
            chat_id,
            user_id,
            next_ver,
        )

        loaded = await self._load_working_memory_conn(conn, chat_id, user_id)
        if loaded is None:
            raise MemoryPersistenceError(
                f"Failed to load memory after appending facts for chat '{chat_id}'."
            )
        return loaded

    def _row_to_memory_fact(self, row: asyncpg.Record) -> MemoryFact:
        return MemoryFact(
            fact_id=row["fact_id"],
            fact_type=row["fact_type"],
            key=row["key"],
            value=json.loads(row["value"]) if row["value"] else None,
            normalized_value=row["normalized_value"] if "normalized_value" in row else None,
            value_type=row["value_type"],
            scope=row["scope"],
            status=row["status"],
            confirmed_by_user=row["confirmed_by_user"],
            provenance=FactProvenance(
                source_turn=row["source_turn"],
                source_excerpt=row["source_excerpt"],
                source_message_id=row["source_message_id"],
                extracted_by=row["extracted_by"],
                confidence=row["confidence"],
            ),
            observed_at=row["observed_at"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
        )
