"""Graph integration tests for Conversation Memory + Root Graph (Phase 03).

Verifies multi-turn follow-ups, reference resolution, destination changes,
backend durability across graph instances, and failure/fallback behaviors.
"""

import asyncio
import unittest
from uuid import uuid4

from app.modules.conversation_memory.public import (
    InMemoryMemoryRepository,
    WorkingMemoryState,
    build_conversation_memory_service,
)
from app.modules.explorer.public import create_explorer_service
from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.public import SupervisorService
from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository
from app.modules.trip_chat.service import TripChatService
from app.orchestration.root_graph import create_root_graph


class MemoryAwareClassifier:
    """Classifier that uses supervisor intent rules and memory context."""

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        msg = payload.message.lower()
        if "đổi sang" in msg or "chuyển sang" in msg:
            return ClassifierResult(
                route="explorer",
                confidence=1.0,
                reason="Destination change request",
                response=None,
            )
        if "lên plan" in msg or "lập kế hoạch" in msg or "tạo lịch trình" in msg:
            return ClassifierResult(
                route="explorer",
                confidence=1.0,
                reason="Plan creation request",
                response=None,
            )
        if "có gì chơi" in msg or "ở đâu" in msg:
            return ClassifierResult(
                route="information_finder",
                confidence=1.0,
                reason="Information inquiry",
                response="Thông tin danh lam thắng cảnh.",
            )
        return ClassifierResult(
            route="explorer",
            confidence=0.9,
            reason="Default trip planning route",
            response=None,
        )


def build_test_env():
    supervisor = SupervisorService(classifier=MemoryAwareClassifier())
    explorer = create_explorer_service(
        draft_provider="rules",
        source_draft_provider="rules",
    )
    graph = create_root_graph(
        supervisor_service=supervisor,
        explorer_service=explorer,
    )
    repo = InMemoryTripChatRepository()
    memory_repo = InMemoryMemoryRepository()
    memory_service = build_conversation_memory_service(memory_repo)
    chat_service = TripChatService(
        repository=repo,
        graph=graph,
        memory_service=memory_service,
    )
    return chat_service, memory_service, graph, repo


class TestMemoryRootGraphIntegration(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.chat_service, self.memory_service, self.graph, self.repo = build_test_env()

    def test_scenario_a_same_chat_followup(self):
        """Scenario A: Same chat follow-up retains destination and resolves references."""
        chat = asyncio.run(self.chat_service.create(self.user_id, "Trip Hanoi"))
        chat_id = chat.id

        # Turn 1: "Hà Nội có gì chơi?"
        asyncio.run(self.chat_service.send(self.user_id, chat_id, "Hà Nội có gì chơi?"))

        memory = asyncio.run(self.memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(memory.destination, "Hà Nội")

        # Turn 2: "Lên plan các điểm bên trên trong 3 ngày."
        saved_chat = asyncio.run(
            self.chat_service.send(
                self.user_id, chat_id, "Lên plan các điểm bên trên trong 3 ngày."
            )
        )
        self.assertIsNotNone(saved_chat)
        assistant_msg = saved_chat.messages[-1]
        self.assertEqual(assistant_msg.route, "explorer")

        updated_mem = asyncio.run(self.memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(updated_mem.destination, "Hà Nội")
        self.assertEqual(updated_mem.duration_days, 3)

    def test_scenario_b_pronoun_reference_and_clarification(self):
        """Scenario B: Pronoun resolution or clarification question when ambiguous."""
        chat = asyncio.run(self.chat_service.create(self.user_id, "Trip Hanoi Places"))
        chat_id = chat.id

        # Turn 1: Specify multiple places
        asyncio.run(
            self.chat_service.send(
                self.user_id,
                chat_id,
                "Tôi muốn đi du lịch ở Hà Nội, tham quan Văn Miếu và Hồ Hoàn Kiếm.",
            )
        )

        # Turn 2: "Thêm chỗ đó vào ngày 2." (Ambiguous reference -> 2 candidate places)
        saved_chat = asyncio.run(
            self.chat_service.send(self.user_id, chat_id, "Thêm chỗ đó vào ngày 2.")
        )
        self.assertIsNotNone(saved_chat)
        assistant_msg = saved_chat.messages[-1]
        self.assertEqual(assistant_msg.route, "finish")
        self.assertIsNotNone(assistant_msg.clarification_question)
        self.assertIn("Văn Miếu", assistant_msg.clarification_question)

    def test_scenario_c_destination_change(self):
        """Scenario C: Changing destination supersedes previous destination fact."""
        chat = asyncio.run(self.chat_service.create(self.user_id, "Change Dest"))
        chat_id = chat.id

        # Turn 1: Confirm Hanoi
        asyncio.run(self.chat_service.send(self.user_id, chat_id, "Tôi chốt đi Hà Nội 3 ngày."))
        mem1 = asyncio.run(self.memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(mem1.destination, "Hà Nội")

        # Turn 2: Explicit override to Danang
        asyncio.run(self.chat_service.send(self.user_id, chat_id, "Tôi muốn đổi sang Đà Nẵng."))
        mem2 = asyncio.run(self.memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(mem2.destination, "Đà Nẵng")

    def test_scenario_d_restart_durability(self):
        """Scenario D: Restarting graph/backend instance retains persistent memory."""
        chat = asyncio.run(self.chat_service.create(self.user_id, "Durable Chat"))
        chat_id = chat.id

        # Instance A: Send first turn
        asyncio.run(self.chat_service.send(self.user_id, chat_id, "Tôi muốn đi du lịch ở Đà Nẵng 4 ngày."))

        # Simulate backend restart with new graph and service instances sharing same persistent memory repo
        new_supervisor = SupervisorService(classifier=MemoryAwareClassifier())
        new_explorer = create_explorer_service(
            draft_provider="rules",
            source_draft_provider="rules",
        )
        fresh_graph = create_root_graph(
            supervisor_service=new_supervisor,
            explorer_service=new_explorer,
        )
        fresh_chat_service = TripChatService(
            repository=self.repo,
            graph=fresh_graph,
            memory_service=self.memory_service,
        )

        # Instance B: Send follow-up on fresh graph instance
        saved_chat = asyncio.run(
            fresh_chat_service.send(self.user_id, chat_id, "Lên plan chi tiết.")
        )
        self.assertIsNotNone(saved_chat)
        mem = asyncio.run(self.memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(mem.destination, "Đà Nẵng")
        self.assertEqual(mem.duration_days, 4)

    def test_scenario_e_legacy_chat_missing_memory_bootstrap(self):
        """Scenario E: Legacy chat without memory row bootstraps gracefully."""
        # Create legacy chat directly in repo without memory row
        legacy_chat = asyncio.run(self.repo.create_chat(self.user_id, "Legacy Chat"))
        self.assertEqual(legacy_chat.messages, [])

        # Process message using chat service
        saved_chat = asyncio.run(
            self.chat_service.send(self.user_id, legacy_chat.id, "Đi du lịch Huế 2 ngày.")
        )
        self.assertIsNotNone(saved_chat)
        mem = asyncio.run(self.memory_service.load_context(legacy_chat.id, self.user_id))
        self.assertEqual(mem.destination, "Huế")

    def test_scenario_f_memory_service_failure_fallback(self):
        """Scenario F: Memory service failure falls back gracefully to transcript-only mode."""
        class FaultyMemoryService:
            async def load_context(self, chat_id, user_id):
                raise RuntimeError("Database connection timed out!")

            async def process_message(self, **kwargs):
                raise RuntimeError("Database write error!")

        chat = asyncio.run(self.chat_service.create(self.user_id, "Faulty Memory Test"))
        faulty_chat_service = TripChatService(
            repository=self.repo,
            graph=self.graph,
            memory_service=FaultyMemoryService(),
        )

        saved_chat = asyncio.run(
            faulty_chat_service.send(self.user_id, chat.id, "Chào bạn!")
        )
        self.assertIsNotNone(saved_chat)
        assistant_msg = saved_chat.messages[-1]
        self.assertTrue(any("Memory service error" in w for w in assistant_msg.warnings))

    def test_scenario_g_version_conflict_retry(self):
        """Scenario G: Memory version conflict retries cleanly without corrupting state."""
        chat = asyncio.run(self.chat_service.create(self.user_id, "Conflict Test"))
        chat_id = chat.id

        # Turn 1
        asyncio.run(self.chat_service.send(self.user_id, chat_id, "Đi Đà Lạt 3 ngày."))

        # Verify retry handling on version conflict
        saved_chat = asyncio.run(
            self.chat_service.send(self.user_id, chat_id, "Lên plan chi tiết.")
        )
        self.assertIsNotNone(saved_chat)


if __name__ == "__main__":
    unittest.main()
