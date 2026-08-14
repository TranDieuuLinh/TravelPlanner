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
    MemoryReference,
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

    def test_real_db_scalar_fact_superseding(self):
        f1 = MemoryFact(
            fact_id=f"f_hn_{os.urandom(4).hex()}",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(source_turn=1, source_excerpt="Đi Hà Nội", extracted_by="rule", confidence=0.9),
        )
        self.loop.run_until_complete(
            self.repo.append_facts(self.test_chat_id, self.user_id, [f1], expected_version=0)
        )

        f2 = MemoryFact(
            fact_id=f"f_dn_{os.urandom(4).hex()}",
            fact_type="destination",
            key="destination",
            value="Đà Nẵng",
            provenance=FactProvenance(source_turn=2, source_excerpt="Đổi sang Đà Nẵng", extracted_by="rule", confidence=0.95),
        )
        saved = self.loop.run_until_complete(
            self.repo.append_facts(self.test_chat_id, self.user_id, [f2], expected_version=1)
        )

        # Assertion c: only Đà Nẵng is active
        self.assertEqual(len(saved.active_facts), 1)
        self.assertEqual(saved.active_facts[0].value, "Đà Nẵng")

        # Assertion d: Hà Nội has status = 'superseded' in DB
        async def check_superseded():
            async with self.pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT status FROM agent_conversation_memory_facts WHERE fact_id = $1;", f1.fact_id
                )
        status_hn = self.loop.run_until_complete(check_superseded())
        self.assertEqual(status_hn, "superseded")

    def test_real_db_source_url_persistence(self):
        wm = WorkingMemoryState(chat_id=self.test_chat_id, user_id=self.user_id)
        f_url = MemoryFact(
            fact_id=f"f_url_{os.urandom(4).hex()}",
            fact_type="note",
            key="note",
            value="https://example.com/hanoi_guide",
            provenance=FactProvenance(
                source_turn=1,
                source_excerpt="xem tai https://example.com/hanoi_guide",
                extracted_by="rule",
                confidence=0.9,
                source_url="https://example.com/hanoi_guide",
            ),
        )
        self.loop.run_until_complete(
            self.repo.save_memory_and_facts(wm, [f_url], expected_version=0)
        )
        loaded = self.loop.run_until_complete(
            self.repo.load_working_memory(self.test_chat_id, self.user_id)
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.active_facts), 1)
        self.assertEqual(loaded.active_facts[0].provenance.source_url, "https://example.com/hanoi_guide")

    def test_real_db_active_references_persistence(self):
        reference = MemoryReference(
            reference_id=f"ref_{os.urandom(4).hex()}",
            phrase="các điểm bên trên",
            reference_type="deictic",
            resolved_entity="Văn Miếu, Hồ Hoàn Kiếm",
            target_fact_ids=["fact_a", "fact_b"],
        )
        wm = WorkingMemoryState(
            chat_id=self.test_chat_id,
            user_id=self.user_id,
            active_references=[reference],
        )
        self.loop.run_until_complete(
            self.repo.save_working_memory(wm, expected_version=0)
        )
        loaded = self.loop.run_until_complete(
            self.repo.load_working_memory(self.test_chat_id, self.user_id)
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.active_references), 1)
        self.assertEqual(loaded.active_references[0].resolved_entity, reference.resolved_entity)
        self.assertEqual(loaded.active_references[0].target_fact_ids, reference.target_fact_ids)

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
