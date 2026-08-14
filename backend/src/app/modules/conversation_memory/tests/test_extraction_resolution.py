"""Unit tests for Phase 02 Fact Extraction, Reference Resolution, and Merge Policies."""

import asyncio
import unittest

from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.extractor import RuleBasedFactExtractor
from app.modules.conversation_memory.merge_policy import MergePolicyEvaluator
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver
from app.modules.conversation_memory.service import ConversationMemoryService
from app.modules.conversation_memory.tests.test_repository import (
    FakeAsyncpgConnection,
    FakeAsyncpgPool,
)


class TestPhase02ExtractionAndResolution(unittest.TestCase):
    def setUp(self):
        self.conn = FakeAsyncpgConnection()
        self.pool = FakeAsyncpgPool(self.conn)
        self.repo = PostgresMemoryRepository(self.pool)
        self.extractor = RuleBasedFactExtractor()
        self.resolver = RuleBasedReferenceResolver()
        self.service = ConversationMemoryService(
            repository=self.repo,
            extractor=self.extractor,
            resolver=self.resolver,
        )
        self.chat_id = "test_phase02_chat"
        self.user_id = 42

    def test_accented_vietnamese_extraction(self):
        memory = WorkingMemoryState(chat_id=self.chat_id, user_id=self.user_id)
        extracted = asyncio.run(self.extractor.extract_facts("Tôi muốn đi Hà Nội 3 ngày", memory, turn=1))
        dest_fact = next((f for f in extracted if f.key == "destination"), None)
        dur_fact = next((f for f in extracted if f.key == "duration"), None)

        self.assertIsNotNone(dest_fact)
        self.assertEqual(dest_fact.value, "Hà Nội")
        self.assertIsNotNone(dur_fact)
        self.assertEqual(dur_fact.value, 3)

    def test_unaccented_vietnamese_extraction(self):
        memory = WorkingMemoryState(chat_id=self.chat_id, user_id=self.user_id)
        extracted = asyncio.run(self.extractor.extract_facts("Toi muon di Ha Noi 3 ngay", memory, turn=1))
        dest_fact = next((f for f in extracted if f.key == "destination"), None)
        dur_fact = next((f for f in extracted if f.key == "duration"), None)

        self.assertIsNotNone(dest_fact)
        self.assertEqual(dest_fact.value, "Hà Nội")
        self.assertIsNotNone(dur_fact)
        self.assertEqual(dur_fact.value, 3)

    def test_common_abbreviations_and_duration_travelers(self):
        memory = WorkingMemoryState(chat_id=self.chat_id, user_id=self.user_id)
        extracted = asyncio.run(self.extractor.extract_facts("Di 3 ngay, 4 nguoi di DN", memory, turn=1))
        dest_fact = next((f for f in extracted if f.key == "destination"), None)
        dur_fact = next((f for f in extracted if f.key == "duration"), None)
        trv_fact = next((f for f in extracted if f.key == "travelers"), None)

        self.assertIsNotNone(dest_fact)
        self.assertEqual(dest_fact.value, "Đà Nẵng")
        self.assertEqual(dur_fact.value, 3)
        self.assertEqual(trv_fact.value, 4)

    def test_explicit_destination_change_vs_hypothetical(self):
        memory = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            destination="Hà Nội",
            active_facts=[
                MemoryFact(
                    fact_id="f_hanoi",
                    fact_type="destination",
                    key="destination",
                    value="Hà Nội",
                    confirmed_by_user=True,
                    provenance=FactProvenance(source_turn=1, source_excerpt="Hà Nội", extracted_by="test", confidence=1.0),
                )
            ]
        )

        hypothetical_facts = asyncio.run(
            self.extractor.extract_facts("Có thể đi Đà Nẵng không?", memory, turn=2)
        )
        merged_hypo = self.service.merge_extracted_facts(memory, hypothetical_facts)
        self.assertEqual(merged_hypo.destination, "Hà Nội")

        change_facts = asyncio.run(
            self.extractor.extract_facts("Đổi sang Đà Nẵng", memory, turn=3)
        )
        merged_change = self.service.merge_extracted_facts(memory, change_facts)
        self.assertEqual(merged_change.destination, "Đà Nẵng")

    def test_confirmed_fact_protection_confidence(self):
        memory = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            destination="Hà Nội",
            active_facts=[
                MemoryFact(
                    fact_id="f_hn_conf",
                    fact_type="destination",
                    key="destination",
                    value="Hà Nội",
                    confirmed_by_user=True,
                    provenance=FactProvenance(source_turn=1, source_excerpt="Tôi chốt Hà Nội", extracted_by="test", confidence=0.95),
                )
            ]
        )
        unconfirmed_fact = MemoryFact(
            fact_id="f_dn_unconf",
            fact_type="destination",
            key="destination",
            value="Đà Nẵng",
            confirmed_by_user=False,
            provenance=FactProvenance(source_turn=2, source_excerpt="Đà Nẵng đẹp", extracted_by="test", confidence=0.8),
        )
        valid = self.service.merge_policy.evaluate_facts(memory, [unconfirmed_fact])
        self.assertEqual(len(valid), 0)

    def test_url_extraction(self):
        memory = WorkingMemoryState(chat_id=self.chat_id, user_id=self.user_id)
        extracted = asyncio.run(
            self.extractor.extract_facts("Xem chi tiết tại https://example.com/hanoi", memory, turn=1, message_id="m_url")
        )
        url_fact = next((f for f in extracted if f.key == "note"), None)
        self.assertIsNotNone(url_fact)
        self.assertEqual(url_fact.provenance.source_url, "https://example.com/hanoi")
        self.assertEqual(url_fact.provenance.source_message_id, "m_url")

    def test_deictic_reference_resolution(self):
        memory = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            mentioned_places=["Văn Miếu", "Hồ Hoàn Kiếm"],
        )
        refs, clarify = asyncio.run(
            self.resolver.resolve_references("Lên plan các điểm bên trên trong 3 ngày", memory)
        )
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].reference_type, "deictic")
        self.assertEqual(refs[0].resolved_entity, "Văn Miếu, Hồ Hoàn Kiếm")
        self.assertFalse(clarify)

    def test_anaphora_reference_resolution_and_competing_candidates(self):
        single_mem = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            mentioned_places=["Văn Miếu"],
        )
        refs_single, clarify_single = asyncio.run(
            self.resolver.resolve_references("Thêm chỗ đó vào ngày 2", single_mem)
        )
        self.assertEqual(len(refs_single), 1)
        self.assertEqual(refs_single[0].resolved_entity, "Văn Miếu")
        self.assertFalse(clarify_single)

        multi_fact1 = MemoryFact(
            fact_id="f_vm", fact_type="place_candidate", key="place_candidate", value="Văn Miếu",
            provenance=FactProvenance(source_turn=1, source_excerpt="txt", extracted_by="test", confidence=0.8)
        )
        multi_fact2 = MemoryFact(
            fact_id="f_hg", fact_type="place_candidate", key="place_candidate", value="Hồ Hoàn Kiếm",
            provenance=FactProvenance(source_turn=1, source_excerpt="txt", extracted_by="test", confidence=0.8)
        )
        multi_mem = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            active_facts=[multi_fact1, multi_fact2],
        )
        refs_multi, clarify_multi = asyncio.run(
            self.resolver.resolve_references("Thêm chỗ đó vào ngày 2", multi_mem)
        )
        self.assertEqual(len(refs_multi), 1)
        self.assertIsNone(refs_multi[0].resolved_entity)
        self.assertTrue(clarify_multi)

    def test_plan_reference_resolution(self):
        memory = WorkingMemoryState(
            chat_id=self.chat_id,
            user_id=self.user_id,
            current_plan_ref="plan_v1_123",
        )
        refs, clarify = asyncio.run(
            self.resolver.resolve_references("Chỉnh sửa lịch trình vừa rồi", memory)
        )
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].reference_type, "plan_ref")
        self.assertEqual(refs[0].resolved_entity, "plan_v1_123")
        self.assertFalse(clarify)

    def test_provenance_fields_and_confidence_bounds(self):
        memory = WorkingMemoryState(chat_id=self.chat_id, user_id=self.user_id)
        facts = asyncio.run(self.extractor.extract_facts("Tôi muốn đi Huế 2 ngày", memory, turn=1, message_id="msg_100"))
        for f in facts:
            self.assertEqual(f.provenance.source_turn, 1)
            self.assertEqual(f.provenance.source_message_id, "msg_100")
            self.assertTrue(len(f.provenance.source_excerpt) <= 200)
            self.assertEqual(f.provenance.extracted_by, "rule_based_v1")
            self.assertTrue(0.0 <= f.provenance.confidence <= 1.0)

    def test_process_message_full_pipeline(self):
        async def run_pipeline():
            mem, extracted, refs, clarify = await self.service.prepare_message_context(
                chat_id=self.chat_id,
                user_id=self.user_id,
                message="Tôi muốn đi Hà Nội 3 ngày, 2 người",
                turn=1,
                message_id="msg_001",
            )
            return await self.service.persist_prepared_context(
                memory=mem,
                facts=extracted,
                expected_version=0,
            ), extracted, refs, clarify

        updated_mem, extracted, refs, clarify = asyncio.run(run_pipeline())
        self.assertEqual(updated_mem.destination, "Hà Nội")
        self.assertEqual(updated_mem.duration_days, 3)
        self.assertEqual(updated_mem.travelers, 2)
        self.assertTrue(updated_mem.version >= 1)
        self.assertFalse(clarify)
        self.assertTrue(len(updated_mem.active_facts) >= 3)
        for cf in updated_mem.confirmed_facts:
            self.assertTrue(cf.confirmed_by_user)
            self.assertEqual(cf.status, "active")


if __name__ == "__main__":
    unittest.main()
