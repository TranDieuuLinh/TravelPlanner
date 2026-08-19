import asyncio
import unittest

from app.modules.conversation_memory.adapters.in_memory import InMemoryMemoryRepository
from app.modules.conversation_memory.contract import FactProvenance, MemoryFact, WorkingMemoryState
from app.modules.conversation_memory.service import ConversationMemoryService


class TestPhase05(unittest.TestCase):
    def test_summary_is_bounded_and_has_provenance_metadata(self):
        service = ConversationMemoryService(InMemoryMemoryRepository())
        memory = WorkingMemoryState(chat_id="chat-5", user_id=1, destination="Hà Nội")
        summary = service.build_summary(
            memory, [f"message {index} " + "x" * 500 for index in range(8)], source_turn_start=3
        )
        self.assertIsNotNone(summary)
        self.assertLessEqual(len(summary.text), 2400)
        self.assertEqual(summary.provider, "rule_based")
        self.assertEqual(summary.source_turn_start, 3)

    def test_only_confirmed_user_facts_are_exposed_and_deletable(self):
        async def scenario():
            service = ConversationMemoryService(InMemoryMemoryRepository())
            fact = MemoryFact(
                fact_id="user-style-1",
                fact_type="travel_style",
                key="style",
                value="ẩm thực",
                confirmed_by_user=True,
                provenance=FactProvenance(
                    source_turn=1,
                    source_excerpt="Tôi thích ẩm thực",
                    extracted_by="user_confirmed",
                    confidence=1.0,
                ),
            )
            await service.remember_user_facts("chat-5", 1, [fact])
            preferences = await service.load_user_preferences(1)
            self.assertEqual(preferences.preferences, ["ẩm thực"])
            self.assertEqual(await service.delete_user_preferences(1), 1)
            self.assertEqual((await service.load_user_preferences(1)).preferences, [])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
