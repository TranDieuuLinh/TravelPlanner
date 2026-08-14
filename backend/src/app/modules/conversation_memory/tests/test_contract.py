"""Unit tests for conversation_memory contracts, snake_case/camelCase serialization, and vocabulary validation."""

import unittest
from pydantic import ValidationError

from app.modules.conversation_memory.contract import normalize_fact_value
from app.modules.conversation_memory.public import (
    FactProvenance,
    MemoryFact,
    MemoryReference,
    RootStateMemoryMapping,
    UserPreferenceMemory,
    WorkingMemoryState,
)


class TestConversationMemoryContract(unittest.TestCase):
    def test_fact_provenance_and_memory_fact_serialization(self):
        provenance = FactProvenance(
            source_turn=1,
            source_excerpt="Hà Nội có gì chơi?",
            source_message_id="msg_001",
            extracted_by="explorer_v1",
            confidence=0.95,
        )
        fact = MemoryFact(
            fact_id="fact_001",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            value_type="string",
            scope="chat",
            status="active",
            provenance=provenance,
            confirmed_by_user=True,
        )

        dumped = fact.model_dump(mode="json", by_alias=True)
        self.assertEqual(dumped["factId"], "fact_001")
        self.assertEqual(dumped["factType"], "destination")
        self.assertEqual(dumped["valueType"], "string")
        self.assertEqual(dumped["scope"], "chat")
        self.assertEqual(dumped["status"], "active")
        self.assertTrue(dumped["confirmedByUser"])
        self.assertEqual(dumped["provenance"]["sourceTurn"], 1)
        self.assertEqual(dumped["provenance"]["sourceExcerpt"], "Hà Nội có gì chơi?")
        self.assertEqual(dumped["provenance"]["sourceMessageId"], "msg_001")

        deserialized = MemoryFact.model_validate(dumped)
        self.assertEqual(deserialized.fact_id, "fact_001")
        self.assertEqual(deserialized.provenance.source_turn, 1)

    def test_normalization_whitespace_casing_equivalence(self):
        n1 = normalize_fact_value("Văn Miếu")
        n2 = normalize_fact_value(" Văn Miếu ")
        n3 = normalize_fact_value("văn  miếu")
        self.assertEqual(n1, "văn miếu")
        self.assertEqual(n1, n2)
        self.assertEqual(n2, n3)

    def test_two_different_facts_distinct_normalized_values(self):
        n_vanmieu = normalize_fact_value("Văn Miếu")
        n_hoguom = normalize_fact_value("Hồ Gươm")
        self.assertNotEqual(n_vanmieu, n_hoguom)

    def test_cannot_bypass_normalization_with_manual_normalized_value(self):
        fact = MemoryFact(
            fact_id="f_bypass",
            fact_type="place_candidate",
            key="place_candidate",
            value="Văn Miếu",
            normalized_value="  VĂN   MIẾU  ",
            provenance=FactProvenance(source_turn=1, source_excerpt="txt", extracted_by="e", confidence=0.8),
        )
        # computed_normalized_value MUST STILL call normalize_fact_value on manual input
        self.assertEqual(fact.computed_normalized_value, "văn miếu")

    def test_source_excerpt_max_length_raises(self):
        long_excerpt = "a" * 201
        with self.assertRaises(ValidationError):
            FactProvenance(
                source_turn=1,
                source_excerpt=long_excerpt,
                extracted_by="test",
                confidence=0.9,
            )

    def test_working_memory_state_complete_phase01_fields(self):
        memory = WorkingMemoryState(
            chat_id="chat_123",
            user_id=42,
            destination="Hà Nội",
            duration_days=3,
            travelers=4,
            budget={"tier": "medium"},
            preferences=["gần trung tâm"],
            avoids=["đường đông"],
            mentioned_places=["Hồ Hoàn Kiếm"],
            selected_places=["Văn Miếu"],
            current_plan_ref="plan_001",
            pending_goal="chọn khách sạn",
            last_route="explorer",
            summary="Thảo luận đi Hà Nội 3 ngày",
            version=2,
            confirmed_facts=[],
            active_references=[
                MemoryReference(
                    reference_id="ref_001",
                    phrase="các điểm bên trên",
                    reference_type="deictic",
                    resolved_entity="Hồ Hoàn Kiếm",
                    target_fact_ids=["fact_001"],
                )
            ],
        )
        dumped = memory.model_dump(mode="json", by_alias=True)
        self.assertEqual(dumped["chatId"], "chat_123")
        self.assertEqual(dumped["durationDays"], 3)
        self.assertEqual(dumped["version"], 2)
        self.assertEqual(dumped["mentionedPlaces"], ["Hồ Hoàn Kiếm"])
        self.assertEqual(dumped["selectedPlaces"], ["Văn Miếu"])
        self.assertEqual(dumped["currentPlanRef"], "plan_001")
        self.assertEqual(dumped["activeReferences"][0]["referenceType"], "deictic")

        self.assertEqual(memory.places, ["Hồ Hoàn Kiếm", "Văn Miếu"])

    def test_user_preference_memory(self):
        pref = UserPreferenceMemory(
            user_id=42,
            preferences=["chay", "yên tĩnh"],
            dietary_restrictions=["chay"],
            preferred_transport=["tàu hỏa"],
            budget_tier="medium",
            confidence=0.9,
            status="active",
            source_message_id="msg_pref_1",
        )
        self.assertEqual(pref.user_id, 42)
        self.assertIn("chay", pref.dietary_restrictions)
        self.assertEqual(pref.confidence, 0.9)

    def test_invalid_fact_type_raises(self):
        with self.assertRaises(ValidationError):
            MemoryFact(
                fact_id="f1",
                fact_type="invalid_type",
                key="k",
                value="v",
                provenance=FactProvenance(
                    source_turn=1, source_excerpt="txt", extracted_by="e", confidence=0.8
                ),
            )

    def test_invalid_reference_type_raises(self):
        with self.assertRaises(ValidationError):
            MemoryReference(
                reference_id="ref_99",
                phrase="cái đó",
                reference_type="invalid_ref_type",
            )

    def test_confidence_bounds_raises(self):
        with self.assertRaises(ValidationError):
            FactProvenance(
                source_turn=1,
                source_excerpt="text",
                extracted_by="test",
                confidence=1.5,
            )

    def test_required_identifiers_raises(self):
        with self.assertRaises(ValidationError):
            WorkingMemoryState(chat_id="", user_id=1)
        with self.assertRaises(ValidationError):
            WorkingMemoryState(chat_id="chat_1", user_id=0)

    def test_forbid_extra_fields_raises(self):
        with self.assertRaises(ValidationError):
            WorkingMemoryState.model_validate(
                {
                    "chatId": "chat_1",
                    "userId": 1,
                    "unknownExtraField": "value",
                }
            )

    def test_unresolved_reference_support(self):
        ref = MemoryReference(
            reference_id="ref_unresolved_1",
            phrase="chỗ đó",
            reference_type="anaphora",
            resolved_entity=None,
            target_fact_ids=[],
        )
        dumped = ref.model_dump(mode="json", by_alias=True)
        self.assertIsNone(dumped["resolvedEntity"])
        self.assertEqual(dumped["targetFactIds"], [])

        deserialized = MemoryReference.model_validate(dumped)
        self.assertIsNone(deserialized.resolved_entity)
        self.assertEqual(deserialized.reference_type, "anaphora")

    def test_root_state_memory_mapping(self):
        wm = WorkingMemoryState(
            chat_id="chat_99",
            user_id=1,
            destination="Đà Nẵng",
        )
        mapping = RootStateMemoryMapping(
            root_request_id="req_001",
            thread_id="chat_99",
            working_memory=wm,
            mapped_from_transcript_count=2,
        )
        self.assertEqual(mapping.thread_id, "chat_99")
        self.assertEqual(mapping.working_memory.destination, "Đà Nẵng")


if __name__ == "__main__":
    unittest.main()
