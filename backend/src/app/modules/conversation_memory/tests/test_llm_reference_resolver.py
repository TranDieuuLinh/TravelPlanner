import asyncio
import json
import unittest

from app.modules.conversation_memory.adapters.llm_reference_resolver import (
    HybridLlmReferenceResolver,
)
from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)


class FakeLlmClient:
    def __init__(self, response: str | Exception):
        self.response = response
        self.calls = []

    async def generate(self, prompt: str, **kwargs) -> str:
        self.calls.append((json.loads(prompt), kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def memory_with_places() -> WorkingMemoryState:
    facts = [
        MemoryFact(
            fact_id=f"place-{index}",
            fact_type="place_candidate",
            key="place_candidate",
            value=name,
            provenance=FactProvenance(
                source_turn=1,
                source_excerpt=name,
                extracted_by="test",
                confidence=0.9,
            ),
        )
        for index, name in enumerate(["Văn Miếu", "Hồ Hoàn Kiếm", "Phố Cổ"], 1)
    ]
    return WorkingMemoryState(
        chat_id="chat-1",
        user_id=1,
        destination="Hà Nội",
        mentioned_places=[str(fact.value) for fact in facts],
        active_facts=facts,
        summary="Người dùng đang tìm địa điểm ở Hà Nội.",
    )


class TestHybridLlmReferenceResolver(unittest.TestCase):
    def test_semantic_place_set_resolves_all_valid_fact_ids(self):
        client = FakeLlmClient(
            json.dumps({
                "kind": "place_set",
                "phrase": "mấy nơi vừa kể",
                "target_fact_ids": ["place-1", "place-2", "place-3"],
                "confidence": 0.96,
                "clarification_required": False,
            })
        )
        refs, clarify = asyncio.run(
            HybridLlmReferenceResolver(client).resolve_references(
                "xếp mấy nơi vừa kể vào hai ngày",
                memory_with_places(),
                recent_messages=["Hà Nội có gì chơi?", "Có Văn Miếu và Hồ Hoàn Kiếm"],
            )
        )
        self.assertFalse(clarify)
        self.assertEqual(refs[0].resolved_entity, "Văn Miếu, Hồ Hoàn Kiếm, Phố Cổ")
        self.assertEqual(refs[0].reference_type, "deictic")
        self.assertEqual(client.calls[0][0]["destination"], "Hà Nội")
        self.assertEqual(len(client.calls[0][0]["recentMessages"]), 2)

    def test_hallucinated_fact_id_is_rejected_and_rules_are_fallback(self):
        client = FakeLlmClient(
            json.dumps({
                "kind": "place_set",
                "phrase": "các điểm bên trên",
                "target_fact_ids": ["made-up"],
                "confidence": 0.99,
                "clarification_required": False,
            })
        )
        refs, clarify = asyncio.run(
            HybridLlmReferenceResolver(client).resolve_references(
                "lên plan các điểm bên trên", memory_with_places()
            )
        )
        self.assertFalse(clarify)
        self.assertEqual(refs[0].target_fact_ids, ["place-1", "place-2", "place-3"])

    def test_provider_error_falls_back_without_breaking_chat(self):
        refs, clarify = asyncio.run(
            HybridLlmReferenceResolver(FakeLlmClient(RuntimeError("offline"))).resolve_references(
                "đi những chỗ đó", memory_with_places()
            )
        )
        self.assertFalse(clarify)
        self.assertEqual(refs[0].resolved_entity, "Văn Miếu, Hồ Hoàn Kiếm, Phố Cổ")

    def test_places_from_transcript_are_allowed_without_hardcoded_facts(self):
        client = FakeLlmClient(
            json.dumps({
                "kind": "place_set",
                "phrase": "những nơi vừa kể",
                "target_fact_ids": [],
                "target_place_names": ["Bảo tàng Phụ nữ", "Nhà tù Hỏa Lò"],
                "confidence": 0.94,
                "clarification_required": False,
            })
        )
        memory = WorkingMemoryState(chat_id="chat-2", user_id=1)

        refs, clarify = asyncio.run(
            HybridLlmReferenceResolver(client).resolve_references(
                "lên lịch những nơi vừa kể",
                memory,
                recent_messages=[
                    "Bạn có thể ghé Bảo tàng Phụ nữ và Nhà tù Hỏa Lò."
                ],
            )
        )

        self.assertFalse(clarify)
        self.assertEqual(
            refs[0].resolved_entity,
            "Bảo tàng Phụ nữ, Nhà tù Hỏa Lò",
        )
