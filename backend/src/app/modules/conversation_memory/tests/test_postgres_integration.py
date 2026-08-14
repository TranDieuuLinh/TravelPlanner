"""Real PostgreSQL Integration Tests for Conversation Memory persistence adapter.

Requires DATABASE_URL environment variable pointing to a reachable PostgreSQL database.
Skips automatically if DATABASE_URL is unavailable or unreachable.
"""

import asyncio
import os
import unittest
import asyncpg

from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import (
    MemoryNotFound,
    MemoryVersionConflict,
)

DATABASE_URL = os.environ.get("DATABASE_URL")


async def is_db_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = asyncio.run(is_db_reachable()) if DATABASE_URL else False


@unittest.skipUnless(DB_AVAILABLE, "Real PostgreSQL database not accessible (DATABASE_URL not set or unreachable)")
class TestPostgresMemoryRepositoryRealIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.pool = cls.loop.run_until_complete(
            asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        )
        migration_path = os.path.join(
            os.path.dirname(__file__), "../../../../../migrations/009_conversation_memory.sql"
        )
        if os.path.exists(migration_path):
            with open(migration_path, "r", encoding="utf-8") as f:
                cls.migration_sql = f.read()
            async def run_mig():
                async with cls.pool.acquire() as conn:
                    await conn.execute(cls.migration_sql)
            cls.loop.run_until_complete(run_mig())
        cls.repo = PostgresMemoryRepository(cls.pool)

    @classmethod
    def tearDownClass(cls):
        cls.loop.run_until_complete(cls.pool.close())
        cls.loop.close()

    def setUp(self):
        self.test_chat_id = f"test_real_chat_{os.urandom(4).hex()}"
        self.user_id = 999999

        async def init_user_and_chat():
            async with self.pool.acquire() as conn:
                has_users_tbl = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_runtime_users';"
                )
                if has_users_tbl:
                    existing_user = await conn.fetchval("SELECT id FROM auth_runtime_users LIMIT 1;")
                    if existing_user:
                        self.user_id = existing_user
                    else:
                        self.user_id = await conn.fetchval(
                            "INSERT INTO auth_runtime_users (email, password_hash) VALUES ($1, 'hash') RETURNING id;",
                            f"test_{os.urandom(4).hex()}@example.com",
                        )

                has_chats_tbl = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_trip_chats';"
                )
                if has_chats_tbl:
                    await conn.execute(
                        "INSERT INTO agent_trip_chats (id, user_id, thread_id, title) VALUES ($1, $2, $1, 'Test Chat') ON CONFLICT DO NOTHING;",
                        self.test_chat_id,
                        self.user_id,
                    )
        self.loop.run_until_complete(init_user_and_chat())

    def tearDown(self):
        async def cleanup():
            async with self.pool.acquire() as conn:
                # The abort test intentionally drops the FK, so facts must be
                # removed explicitly before deleting their parent memories.
                await conn.execute(
                    "DELETE FROM agent_conversation_memory_facts WHERE chat_id LIKE 'test_real_%' OR chat_id LIKE 'chat_legacy_%' OR chat_id LIKE 'chat_orphan_%' OR chat_id = $1;",
                    self.test_chat_id,
                )
                await conn.execute(
                    "DELETE FROM agent_conversation_memory WHERE chat_id LIKE 'test_real_%' OR chat_id LIKE 'chat_legacy_%' OR chat_id LIKE 'chat_orphan_%' OR chat_id = $1;", self.test_chat_id
                )
                has_chats_tbl = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_trip_chats';"
                )
                if has_chats_tbl:
                    await conn.execute(
                        "DELETE FROM agent_trip_chats WHERE id LIKE 'test_real_%' OR id LIKE 'chat_legacy_%' OR id LIKE 'chat_orphan_%' OR id = $1;", self.test_chat_id
                    )
        self.loop.run_until_complete(cleanup())

    def test_real_db_legacy_migration_aborts_on_integrity_violations(self):
        """Legacy ownership/orphan violations abort migration without silent repair."""
        async def legacy_test_flow():
            async with self.pool.acquire() as conn:
                leg_chat = f"chat_legacy_{os.urandom(4).hex()}"
                orphan_chat = f"chat_orphan_{os.urandom(4).hex()}"

                has_chats_tbl = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_trip_chats';"
                )
                if has_chats_tbl:
                    await conn.execute(
                        "INSERT INTO agent_trip_chats (id, user_id, thread_id, title) VALUES ($1, $2, $1, 'Legacy Chat') ON CONFLICT DO NOTHING;",
                        leg_chat, self.user_id
                    )
                    await conn.execute(
                        "INSERT INTO agent_trip_chats (id, user_id, thread_id, title) VALUES ($1, $2, $1, 'Orphan Chat') ON CONFLICT DO NOTHING;",
                        orphan_chat, self.user_id
                    )

                # Drop composite FK constraint and unique index temporarily to simulate pre-migration legacy database state
                await conn.execute("ALTER TABLE agent_conversation_memory_facts DROP CONSTRAINT IF EXISTS fk_conv_memory_facts_parent;")
                await conn.execute("DROP INDEX IF EXISTS idx_agent_conv_memory_facts_active_norm;")

                # 1. Create parent memory for legacy chat using self.user_id
                await conn.execute(
                    "INSERT INTO agent_conversation_memory (chat_id, user_id, version) VALUES ($1, $2, 1) ON CONFLICT DO NOTHING;",
                    leg_chat, self.user_id
                )

                # 2. Insert fact 1 (unconfirmed, lower confidence, unnormalized value)
                f1_id = f"f_leg1_{os.urandom(4).hex()}"
                await conn.execute(
                    """
                    INSERT INTO agent_conversation_memory_facts (
                        fact_id, chat_id, user_id, fact_type, key, value, normalized_value,
                        scope, status, confirmed_by_user, confidence, source_turn, source_excerpt, extracted_by
                    ) VALUES ($1, $2, $3, 'place_candidate', 'place_candidate', '"  Văn   Miếu  "'::jsonb, '', 'chat', 'active', false, 0.8, 1, 'Văn Miếu', 'legacy');
                    """,
                    f1_id, leg_chat, self.user_id
                )

                # 3. Insert fact 2 (duplicate active fact with same normalized string, higher confidence)
                f2_id = f"f_leg2_{os.urandom(4).hex()}"
                await conn.execute(
                    """
                    INSERT INTO agent_conversation_memory_facts (
                        fact_id, chat_id, user_id, fact_type, key, value, normalized_value,
                        scope, status, confirmed_by_user, confidence, source_turn, source_excerpt, extracted_by
                    ) VALUES ($1, $2, $3, 'place_candidate', 'place_candidate', '"văn  miếu"'::jsonb, '', 'chat', 'active', true, 0.95, 2, 'văn miếu', 'legacy');
                    """,
                    f2_id, leg_chat, self.user_id
                )

                # 4. Insert fact 3 (mismatched user_id 888888 instead of parent self.user_id)
                f3_id = f"f_leg3_{os.urandom(4).hex()}"
                await conn.execute(
                    """
                    INSERT INTO agent_conversation_memory_facts (
                        fact_id, chat_id, user_id, fact_type, key, value, normalized_value,
                        scope, status, confirmed_by_user, confidence, source_turn, source_excerpt, extracted_by
                    ) VALUES ($1, $2, 888888, 'destination', 'destination', '"Hà Nội"'::jsonb, '', 'chat', 'active', false, 0.9, 1, 'Hà Nội', 'legacy');
                    """,
                    f3_id, leg_chat
                )

                # 5. Insert fact 4 (orphan fact whose chat_id does not exist in memory table)
                f4_id = f"f_leg4_{os.urandom(4).hex()}"
                await conn.execute(
                    """
                    INSERT INTO agent_conversation_memory_facts (
                        fact_id, chat_id, user_id, fact_type, key, value, normalized_value,
                        scope, status, confirmed_by_user, confidence, source_turn, source_excerpt, extracted_by
                    ) VALUES ($1, $2, $3, 'duration', 'duration', '3'::jsonb, '', 'chat', 'active', false, 0.9, 1, '3 ngày', 'legacy');
                    """,
                    f4_id, orphan_chat, self.user_id
                )

                # The migration must fail and rollback instead of rewriting ownership
                # or creating synthetic parent/chat rows.
                with self.assertRaises(asyncpg.CheckViolationError):
                    # Run the failing migration on a separate checkout so the
                    # failed transaction is rolled back before assertions below.
                    async with self.pool.acquire() as migration_conn:
                        await migration_conn.execute(self.migration_sql)

                # The transaction rollback preserves the legacy evidence for an operator
                # to inspect and repair explicitly.
                self.assertEqual(
                    await conn.fetchval(
                        "SELECT user_id FROM agent_conversation_memory_facts WHERE fact_id = $1;",
                        f3_id,
                    ),
                    888888,
                )
                self.assertIsNone(
                    await conn.fetchval(
                        "SELECT version FROM agent_conversation_memory WHERE chat_id = $1;",
                        orphan_chat,
                    )
                )

        self.loop.run_until_complete(legacy_test_flow())

    def test_real_db_migration_upgrade_and_travelers_column(self):
        async def query_travelers():
            async with self.pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'agent_conversation_memory' AND column_name = 'travelers';"
                )
        col = self.loop.run_until_complete(query_travelers())
        self.assertEqual(col, "travelers")

    def test_real_db_save_and_load(self):
        wm = WorkingMemoryState(
            chat_id=self.test_chat_id,
            user_id=self.user_id,
            destination="Hội An",
            duration_days=3,
            travelers=2,
            budget={"tier": "mid"},
            preferences=["phố cổ"],
        )
        saved = self.loop.run_until_complete(
            self.repo.save_working_memory(wm, expected_version=0)
        )
        self.assertEqual(saved.version, 1)
        self.assertEqual(saved.travelers, 2)

        loaded = self.loop.run_until_complete(
            self.repo.load_working_memory(self.test_chat_id, self.user_id)
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.destination, "Hội An")
        self.assertEqual(loaded.travelers, 2)

    def test_real_db_multiple_place_candidates_allowed(self):
        f1 = MemoryFact(
            fact_id=f"f_real_p1_{os.urandom(4).hex()}",
            fact_type="place_candidate",
            key="place_candidate",
            value="Văn Miếu",
            provenance=FactProvenance(source_turn=1, source_excerpt="Văn Miếu", extracted_by="test", confidence=0.9),
        )
        f2 = MemoryFact(
            fact_id=f"f_real_p2_{os.urandom(4).hex()}",
            fact_type="place_candidate",
            key="place_candidate",
            value="Hồ Hoàn Kiếm",
            provenance=FactProvenance(source_turn=1, source_excerpt="Hồ Hoàn Kiếm", extracted_by="test", confidence=0.9),
        )
        saved = self.loop.run_until_complete(
            self.repo.append_facts(self.test_chat_id, self.user_id, [f1, f2], expected_version=0)
        )
        self.assertEqual(len(saved.active_facts), 2)

    def test_real_db_normalized_deduplication_supersedes(self):
        f1 = MemoryFact(
            fact_id=f"f_real_n1_{os.urandom(4).hex()}",
            fact_type="place_candidate",
            key="place_candidate",
            value=" Văn Miếu ",
            provenance=FactProvenance(source_turn=1, source_excerpt="Văn Miếu", extracted_by="test", confidence=0.9),
        )
        self.loop.run_until_complete(
            self.repo.append_facts(self.test_chat_id, self.user_id, [f1], expected_version=0)
        )

        f2 = MemoryFact(
            fact_id=f"f_real_n2_{os.urandom(4).hex()}",
            fact_type="place_candidate",
            key="place_candidate",
            value="văn  miếu",
            provenance=FactProvenance(source_turn=2, source_excerpt="văn miếu", extracted_by="test", confidence=0.95),
        )
        saved = self.loop.run_until_complete(
            self.repo.append_facts(self.test_chat_id, self.user_id, [f2], expected_version=1)
        )
        self.assertEqual(len(saved.active_facts), 1)
        self.assertEqual(saved.active_facts[0].fact_id, f2.fact_id)

    def test_real_db_composite_fk_mismatch_user_id_fails(self):
        wm = WorkingMemoryState(chat_id=self.test_chat_id, user_id=self.user_id)
        self.loop.run_until_complete(self.repo.save_working_memory(wm, expected_version=0))

        async def insert_bad_fact():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_conversation_memory_facts (
                        fact_id, chat_id, user_id, fact_type, key, value, value_type,
                        scope, status, confirmed_by_user, confidence, source_turn,
                        source_excerpt, extracted_by
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14);
                    """,
                    f"f_bad_{os.urandom(4).hex()}",
                    self.test_chat_id,
                    888888,
                    "destination",
                    "destination",
                    '"Huế"',
                    "string",
                    "chat",
                    "active",
                    False,
                    0.9,
                    1,
                    "Huế",
                    "test",
                )

        with self.assertRaises(asyncpg.ForeignKeyViolationError):
            self.loop.run_until_complete(insert_bad_fact())

    def test_real_db_version_concurrency_conflict(self):
        wm = WorkingMemoryState(chat_id=self.test_chat_id, user_id=self.user_id, destination="Cần Thơ")
        saved = self.loop.run_until_complete(self.repo.save_working_memory(wm, expected_version=0))

        with self.assertRaises(MemoryVersionConflict):
            self.loop.run_until_complete(
                self.repo.save_working_memory(wm, expected_version=0)
            )

        updated = wm.model_copy(update={"version": saved.version, "destination": "Sapa"})
        saved2 = self.loop.run_until_complete(
            self.repo.save_working_memory(updated, expected_version=1)
        )
        self.assertEqual(saved2.version, 2)
        self.assertEqual(saved2.destination, "Sapa")


if __name__ == "__main__":
    unittest.main()
