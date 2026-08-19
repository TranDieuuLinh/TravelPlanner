"""Unit tests for ConversationMemoryService domain behavior and merge policies."""

import asyncio
import unittest

from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import MemoryVersionConflict
from app.modules.conversation_memory.service import ConversationMemoryService
from app.modules.conversation_memory.tests.test_repository import (
    FakeAsyncpgConnection,
    FakeAsyncpgPool,
)


class TestConversationMemoryService(unittest.TestCase):
    def setUp(self):
        self.conn = FakeAsyncpgConnection()
        self.pool = FakeAsyncpgPool(self.conn)
        self.repo = PostgresMemoryRepository(pool=self.pool)
        self.service = ConversationMemoryService(repository=self.repo)

    def test_initialize_empty_memory(self):
        memory = asyncio.run(self.service.initialize_empty_memory(chat_id="chat_init", user_id=42))
        self.assertEqual(memory.chat_id, "chat_init")
        self.assertEqual(memory.user_id, 42)
        self.assertEqual(memory.version, 0)
        self.assertEqual(memory.mentioned_places, [])
        self.assertEqual(memory.selected_places, [])

    def test_load_context_missing_initializes_empty(self):
        memory = asyncio.run(self.service.load_context(chat_id="chat_missing", user_id=42))
        self.assertEqual(memory.chat_id, "chat_missing")
        self.assertEqual(memory.user_id, 42)
        self.assertEqual(memory.version, 0)

    def test_save_working_memory(self):
        initial = asyncio.run(self.service.load_context(chat_id="chat_save", user_id=42))
        updated = initial.model_copy(update={"destination": "Sapa", "duration_days": 4})
        saved = asyncio.run(self.service.save_working_memory(updated, expected_version=0))
        self.assertEqual(saved.destination, "Sapa")
        self.assertEqual(saved.version, 1)

    def test_append_facts_without_expected_version_new_chat(self):
        fact = MemoryFact(
            fact_id="fact_auto_1",
            fact_type="destination",
            key="destination",
            value="Phú Quốc",
            provenance=FactProvenance(source_turn=1, source_excerpt="Phú Quốc", extracted_by="test", confidence=0.9),
        )
        res = asyncio.run(self.service.append_facts("chat_auto_new", 1, [fact]))
        self.assertEqual(res.version, 1)
        self.assertEqual(len(res.active_facts), 1)

    def test_append_facts_without_expected_version_existing_chat(self):
        fact1 = MemoryFact(
            fact_id="fact_auto_ex1",
            fact_type="destination",
            key="destination",
            value="Nha Trang",
            provenance=FactProvenance(source_turn=1, source_excerpt="Nha Trang", extracted_by="test", confidence=0.9),
        )
        saved1 = asyncio.run(self.service.append_facts("chat_auto_ex", 1, [fact1]))
        self.assertEqual(saved1.version, 1)

        fact2 = MemoryFact(
            fact_id="fact_auto_ex2",
            fact_type="duration",
            key="duration",
            value=3,
            value_type="int",
            provenance=FactProvenance(source_turn=2, source_excerpt="3 ngày", extracted_by="test", confidence=0.9),
        )
        saved2 = asyncio.run(self.service.append_facts("chat_auto_ex", 1, [fact2]))
        self.assertEqual(saved2.version, 2)
        self.assertEqual(len(saved2.active_facts), 2)

    def test_append_facts_stale_version_raises_conflict(self):
        fact1 = MemoryFact(
            fact_id="fact_stale_1",
            fact_type="destination",
            key="destination",
            value="Huế",
            provenance=FactProvenance(source_turn=1, source_excerpt="Huế", extracted_by="test", confidence=0.9),
        )
        asyncio.run(self.service.append_facts("chat_stale", 1, [fact1]))

        # Pass stale expected_version 0 when current version is 1
        fact2 = MemoryFact(
            fact_id="fact_stale_2",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(source_turn=2, source_excerpt="Hà Nội", extracted_by="test", confidence=0.9),
        )
        with self.assertRaises(MemoryVersionConflict):
            asyncio.run(self.service.append_facts("chat_stale", 1, [fact2], expected_version=0))

    def test_concurrent_updates_prevent_lost_update(self):
        initial = asyncio.run(self.service.load_context(chat_id="chat_conc_srv", user_id=1))
        # Initial save to establish version 1
        saved1 = asyncio.run(self.service.save_working_memory(initial.model_copy(update={"destination": "Hà Giang"}), expected_version=0))
        self.assertEqual(saved1.version, 1)

        # Two callers load state at version 1
        m1 = asyncio.run(self.service.load_context(chat_id="chat_conc_srv", user_id=1))
        m2 = asyncio.run(self.service.load_context(chat_id="chat_conc_srv", user_id=1))

        # First caller updates to Sapa (version 1 -> 2)
        u1 = asyncio.run(self.service.save_working_memory(m1.model_copy(update={"destination": "Sapa"}), expected_version=1))
        self.assertEqual(u1.version, 2)

        # Second caller attempts update with stale version 1 -> raises MemoryVersionConflict
        with self.assertRaises(MemoryVersionConflict):
            asyncio.run(self.service.save_working_memory(m2.model_copy(update={"destination": "Đà Lạt"}), expected_version=1))

    def test_merge_policy_confirmed_fact_protection(self):
        confirmed_fact = MemoryFact(
            fact_id="fact_conf_1",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(source_turn=1, source_excerpt="Tôi chốt đi Hà Nội", extracted_by="user", confidence=1.0),
            confirmed_by_user=True,
        )
        asyncio.run(self.service.append_facts("chat_policy", 1, [confirmed_fact], expected_version=0))

        unconfirmed_fact = MemoryFact(
            fact_id="fact_unconf_1",
            fact_type="destination",
            key="destination",
            value="Đà Nẵng",
            provenance=FactProvenance(source_turn=2, source_excerpt="Có thể đi Đà Nẵng không?", extracted_by="llm", confidence=0.6),
            confirmed_by_user=False,
        )
        res = asyncio.run(self.service.append_facts("chat_policy", 1, [unconfirmed_fact], expected_version=1))
        self.assertEqual(len(res.confirmed_facts), 1)
        self.assertEqual(res.confirmed_facts[0].value, "Hà Nội")

    def test_mentioned_places_distinct_from_selected_places(self):
        memory = WorkingMemoryState(
            chat_id="chat_places",
            user_id=1,
            mentioned_places=["Hồ Hoàn Kiếm", "Chợ Đồng Xuân"],
            selected_places=["Văn Miếu"],
        )
        saved = asyncio.run(self.service.save_working_memory(memory, expected_version=0))
        self.assertIn("Chợ Đồng Xuân", saved.mentioned_places)
        self.assertNotIn("Chợ Đồng Xuân", saved.selected_places)
        self.assertEqual(saved.selected_places, ["Văn Miếu"])


if __name__ == "__main__":
    unittest.main()
