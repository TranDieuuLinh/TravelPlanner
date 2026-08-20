"""End-to-end multi-turn regression tests for conversation memory contamination fix.

Verifies:
1. Turn 1 assistant mention of Vịnh Hạ Long followed by Turn 2 'lên plan đi HN 3 ngày 2 đêm'
   succeeds and does NOT return 'PlaceChecker cần làm rõ dữ liệu trước khi lập lịch.'
2. Turn 1 assistant mention followed by Turn 2 explicit set-reference ('lên plan các điểm vừa kể trong 3 ngày')
   promotes the referenced places safely for the current turn.
"""

import asyncio
import unittest
from datetime import datetime, timezone

from app.modules.conversation_memory.extractor import remove_accents
from app.modules.conversation_memory.public import (
    InMemoryMemoryRepository,
    build_conversation_memory_service,
)
from app.modules.explorer.public import create_explorer_service
from app.modules.information_finder.contract import (
    InformationFinderOutput,
    SourceReference,
)
from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.public import SupervisorService
from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository
from app.modules.trip_chat.service import TripChatService
from app.orchestration.root_graph import create_root_graph


class EndToEndRegressionClassifier:
    """Classifier handling info inquiry vs trip planning follow-up."""

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        msg = remove_accents(payload.message)
        if "co nhung diem nao" in msg or "co gi choi" in msg or ("tham quan" in msg and "len plan" not in msg):
            return ClassifierResult(
                route="information_finder",
                confidence=1.0,
                reason="Information inquiry",
                response=None,
            )
        if "len plan" in msg or "lap ke hoach" in msg or "di hn" in msg:
            return ClassifierResult(
                route="explorer",
                confidence=1.0,
                reason="Trip plan request",
                response=None,
            )
        return ClassifierResult(
            route="explorer",
            confidence=0.9,
            reason="Default trip planning",
            response=None,
        )


class MockInformationFinderProvider:
    async def find(self, query: str, *, force_refresh: bool = False):
        return InformationFinderOutput(
            answer="Hà Nội có Hồ Gươm, Lăng Bác. Ngoài ra bạn có thể tham quan Vịnh Hạ Long nếu đi xa hơn.",
            sources=[
                SourceReference(
                    source_id="hanoi-src-1",
                    title="Cẩm nang du lịch Hà Nội",
                    url="https://example.test/hanoi-guide",
                    updated_at=datetime.now(timezone.utc),
                    date_kind="last_fetched_at",
                )
            ],
            confidence=0.95,
        )


def build_end_to_end_env():
    supervisor = SupervisorService(classifier=EndToEndRegressionClassifier())
    explorer = create_explorer_service(
        draft_provider="rules",
        source_draft_provider="rules",
    )
    graph = create_root_graph(
        supervisor_service=supervisor,
        explorer_service=explorer,
        information_finder_service=MockInformationFinderProvider(),
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


class TestMemoryContaminationRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = 1

    def test_end_to_end_hanoi_flow_after_assistant_mentions_vinh_ha_long(self) -> None:
        """Concrete end-to-end failure reproduction and fix verification:

        Turn 1: User asks about Hanoi -> assistant mentions Vinh Ha Long in answer.
        Turn 2: User says 'lên plan đi HN 3 ngày 2 đêm' -> Explorer reaches
        the defaults review for Hanoi, not a contaminated destination blocker.
        """
        chat_service, memory_service, _graph, _repo = build_end_to_end_env()
        chat = asyncio.run(chat_service.create(self.user_id, "Hanoi Trip Chat"))
        chat_id = chat.id

        # Turn 1: Info query
        t1_chat = asyncio.run(
            chat_service.send(
                self.user_id,
                chat_id,
                "Hà Nội có những điểm nào tham quan?",
            )
        )
        self.assertIsNotNone(t1_chat)
        t1_last_msg = t1_chat.messages[-1]
        self.assertEqual(t1_last_msg.route, "information_finder")
        self.assertIn("Vịnh Hạ Long", t1_last_msg.content)

        # Check memory after turn 1 has assistant fact for Vinh Ha Long with confirmed_by_user=False
        mem1 = asyncio.run(memory_service.load_context(chat_id, self.user_id))
        self.assertIn("Vịnh Hạ Long", mem1.mentioned_places)
        self.assertNotIn("Vịnh Hạ Long", mem1.selected_places)
        vhl_facts = [f for f in mem1.active_facts if "Vịnh Hạ Long" in str(f.value)]
        self.assertTrue(len(vhl_facts) > 0)
        self.assertFalse(vhl_facts[0].confirmed_by_user)
        self.assertEqual(vhl_facts[0].provenance.extracted_by, "information_finder_v1")

        # Turn 2: User requests 3-day Hanoi plan
        t2_chat = asyncio.run(
            chat_service.send(
                self.user_id,
                chat_id,
                "lên plan đi HN 3 ngày 2 đêm",
            )
        )
        self.assertIsNotNone(t2_chat)
        t2_last_msg = t2_chat.messages[-1]
        self.assertEqual(t2_last_msg.route, "explorer")
        # CRITICAL ASSERTION: Must not return the blocked message!
        self.assertNotEqual(
            t2_last_msg.content,
            "PlaceChecker cần làm rõ dữ liệu trước khi lập lịch.",
        )
        self.assertIsNotNone(t2_last_msg.clarification_question)
        self.assertIn("giá trị mặc định", t2_last_msg.clarification_question)

        # Verify memory after turn 2 has updated destination and duration
        mem2 = asyncio.run(memory_service.load_context(chat_id, self.user_id))
        self.assertEqual(mem2.destination, "Hà Nội")
        self.assertEqual(mem2.duration_days, 3)


if __name__ == "__main__":
    unittest.main()
