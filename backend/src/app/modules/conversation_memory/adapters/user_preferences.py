"""PostgreSQL persistence helpers for user-scoped confirmed preferences."""

import json

from app.modules.conversation_memory.contract import UserPreferenceMemory


class PostgresUserPreferenceMixin:
    async def load_user_preferences(self, user_id: int) -> UserPreferenceMemory:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fact_type, key, value, confidence
                FROM agent_conversation_memory_facts
                WHERE user_id = $1 AND scope = 'user'
                  AND status = 'active' AND confirmed_by_user = true
                ORDER BY created_at ASC;
                """,
                user_id,
            )
        facts = []
        for row in rows:
            value = row["value"]
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            facts.append((row["fact_type"], row["key"], value, row["confidence"]))
        preferences = [str(value) for kind, _, value, _ in facts if kind == "travel_style"]
        dietary = [str(value) for _, key, value, _ in facts if key == "dietary_restriction"]
        budget = next((str(value) for kind, _, value, _ in facts if kind == "budget_tier"), None)
        return UserPreferenceMemory(
            user_id=user_id,
            preferences=list(dict.fromkeys(preferences)),
            dietary_restrictions=list(dict.fromkeys(dietary)),
            budget_tier=budget,
            confidence=min((confidence for *_, confidence in facts), default=1.0),
        )

    async def delete_user_preferences(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                WITH changed AS (
                    UPDATE agent_conversation_memory_facts
                    SET status = 'rejected', updated_at = now()
                    WHERE user_id = $1 AND scope = 'user' AND status = 'active'
                    RETURNING fact_id
                ) SELECT count(*)::int FROM changed;
                """,
                user_id,
            )
