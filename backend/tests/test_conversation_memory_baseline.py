"""Integration baseline tests for conversation_memory (Phase 00).

Demonstrates current system behavior and baseline gaps prior to
implementing the conversation memory vertical feature module:
1. Turn 1 extracts facts ("Hà Nội có gì chơi?").
2. Turn 2 ("Lên plan các điểm bên trên trong 3 ngày.") demonstrates deictic reference gap.
3. Turn 3 ("Thêm chỗ đó vào ngày 2.") demonstrates unresolved pronoun reference gap.
4. State loss on backend restart due to in-memory checkpointer gap (same thread_id on fresh graph).
5. User destination change policy contract representation.
"""

import asyncio
import unittest
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from app.modules.conversation_memory.public import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.explorer.public import create_explorer_service
from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.public import SupervisorService
from app.orchestration.root_graph import create_root_graph


class StubIntentClassifier:
    """Fake classifier returning deterministic route without calling Gemini LLM."""

    def __init__(self, route: str = "explorer", confidence: float = 1.0) -> None:
        self.route = route
        self.confidence = confidence

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        return ClassifierResult(
            route=self.route,
            confidence=self.confidence,
            reason="deterministic baseline route",
            response=None,
        )


def build_test_root_graph(checkpointer: MemorySaver | bool | None = False):
    """Build root graph with fake/stub supervisor and rule-based explorer for deterministic testing.

    Defaults to checkpointer=False for single/multi-turn tests (Cases 01-03, 05) to avoid
    unregistered type serialization warnings when persistence is not being tested.
    Case 04 explicitly passes MemorySaver() to test volatile checkpointer behavior across graph instances.
    """
    supervisor_service = SupervisorService(classifier=StubIntentClassifier())
    explorer_service = create_explorer_service(
        draft_provider="rules",
        source_draft_provider="rules",
    )
    return create_root_graph(
        checkpointer=checkpointer,
        supervisor_service=supervisor_service,
        explorer_service=explorer_service,
    )


class TestConversationMemoryBaseline(unittest.TestCase):
    def setUp(self):
        self.thread_id = str(uuid4())
        self.config = {"configurable": {"thread_id": self.thread_id}}
        self.graph = build_test_root_graph(checkpointer=False)


    def test_case_01_single_turn_explorer_baseline(self):
        """Turn 1: Single turn explorer baseline query prior to memory fact extraction."""
        result = asyncio.run(
            self.graph.ainvoke(
                {"request_id": "turn-1", "message": "Hà Nội có gì chơi?"},
                config=self.config,
            )
        )
        self.assertEqual(result["decision"].route, "explorer")
        self.assertEqual(result["explorer_output"].input_adm, "Hanoi")
        self.assertIsNotNone(result.get("response"))

    def test_case_02_multiturn_deictic_reference_baseline_gap(self):
        """Turn 2: 'Lên plan các điểm bên trên trong 3 ngày.' demonstrates baseline gap."""
        # Turn 1: "Hà Nội có gì chơi?"
        asyncio.run(
            self.graph.ainvoke(
                {"request_id": "turn-1", "message": "Hà Nội có gì chơi?"},
                config=self.config,
            )
        )
        # Turn 2: 'Lên plan các điểm bên trên trong 3 ngày.'
        result_turn2 = asyncio.run(
            self.graph.ainvoke(
                {"request_id": "turn-2", "message": "Lên plan các điểm bên trên trong 3 ngày."},
                config=self.config,
            )
        )
        # Baseline check: Without conversation memory resolution, Turn 2 lacks destination
        # and returns clarification question instead of resolving "các điểm bên trên".
        self.assertEqual(result_turn2["decision"].route, "explorer")
        self.assertEqual(result_turn2["explorer_output"].status, "clarification")
        self.assertEqual(
            result_turn2["clarification_question"],
            "Bạn muốn đi tỉnh hoặc thành phố nào?",
        )
        self.assertIsNone(result_turn2.get("planner_output"))
        self.assertIsNone(result_turn2.get("itinerary"))

    def test_case_03_pronoun_reference_baseline_gap(self):
        """Turn 2: 'Thêm chỗ đó vào ngày 2.' demonstrates unresolved pronoun reference gap."""
        # Turn 1: Provide place and destination context
        asyncio.run(
            self.graph.ainvoke(
                {
                    "request_id": "turn-1",
                    "message": "Tôi muốn đi du lịch ở Hà Nội 3 ngày, tham quan Văn Miếu Quốc Tử Giám.",
                },
                config=self.config,
            )
        )
        # Turn 2: Follow up with anaphoric pronoun reference
        result_turn2 = asyncio.run(
            self.graph.ainvoke(
                {"request_id": "turn-2", "message": "Thêm chỗ đó vào ngày 2."},
                config=self.config,
            )
        )
        # Baseline check: "chỗ đó" is unresolved. Explorer output has no destination or resolved place.
        self.assertEqual(result_turn2["decision"].route, "explorer")
        self.assertIsNone(result_turn2.get("planner_output"))
        self.assertIsNone(result_turn2.get("itinerary"))
        explorer_output = result_turn2.get("explorer_output")
        places = explorer_output.places if (explorer_output and explorer_output.places is not None) else []
        extracted_place_names = [p.name for p in places]
        self.assertNotIn("Văn Miếu Quốc Tử Giám", extracted_place_names)



    def test_case_04_restart_checkpoint_memory_loss_baseline(self):
        """Demonstrates memory loss using a fresh graph instance with a volatile checkpointer (InMemorySaver).

        Note: This tests that InMemorySaver is non-durable across graph instances reusing the same thread_id.
        It is NOT a full container/process restart integration test. Full persistence integration tests are reserved for Phase 01/05.
        """
        fixed_thread_id = self.thread_id
        fixed_config = {"configurable": {"thread_id": fixed_thread_id}}

        # Process A instance
        graph_a = build_test_root_graph(checkpointer=MemorySaver())
        asyncio.run(
            graph_a.ainvoke(
                {"request_id": "session-1", "message": "Tôi muốn đi du lịch ở Đà Nẵng 4 ngày."},
                config=fixed_config,
            )
        )

        # Simulate backend restart by instantiating a fresh graph instance (Process B) with a new volatile checkpointer
        graph_b = build_test_root_graph(checkpointer=MemorySaver())

        result_after_restart = asyncio.run(
            graph_b.ainvoke(
                {"request_id": "session-2", "message": "Tóm tắt lại kế hoạch của tôi."},
                config=fixed_config,  # Reuse EXACT SAME thread_id
            )
        )
        # Baseline check: InMemorySaver in graph B has no state for fixed_thread_id; context is lost
        self.assertEqual(result_after_restart["decision"].route, "explorer")
        self.assertEqual(result_after_restart["explorer_output"].status, "clarification")
        self.assertEqual(
            result_after_restart["clarification_question"],
            "Bạn muốn đi tỉnh hoặc thành phố nào?",
        )
        self.assertIsNone(result_after_restart.get("planner_output"))
        self.assertIsNone(result_after_restart.get("itinerary"))


    def test_case_05_user_destination_change_policy_contract(self):
        """Validates contract structure for representing multiple historical destination facts with provenance.

        Note: Real merge/stale/confirmation policy will be implemented in Phase 02, not implemented in Phase 00 baseline.
        """
        fact_hanoi = MemoryFact(
            fact_id="fact_dest_1",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(
                source_turn=1,
                source_text="Hà Nội có gì chơi?",
                extracted_by="explorer",
                confidence=0.9,
            ),
            confirmed_by_user=True,
        )
        fact_danang = MemoryFact(
            fact_id="fact_dest_2",
            fact_type="destination",
            key="destination",
            value="Đà Nẵng",
            provenance=FactProvenance(
                source_turn=2,
                source_text="Tôi muốn đổi sang đi Đà Nẵng",
                extracted_by="user_override",
                confidence=1.0,
            ),
            confirmed_by_user=True,
        )
        wm = WorkingMemoryState(
            chat_id=self.thread_id,
            user_id=1,
            destination="Đà Nẵng",
            confirmed_facts=[fact_hanoi, fact_danang],
        )

        self.assertEqual(wm.destination, "Đà Nẵng")
        self.assertEqual(len(wm.confirmed_facts), 2)
        self.assertEqual(wm.confirmed_facts[0].value, "Hà Nội")
        self.assertEqual(wm.confirmed_facts[0].provenance.source_turn, 1)
        self.assertEqual(wm.confirmed_facts[1].value, "Đà Nẵng")
        self.assertEqual(wm.confirmed_facts[1].provenance.source_turn, 2)


if __name__ == "__main__":
    unittest.main()

