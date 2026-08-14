"""Bounded, deterministic rolling summary used when transcript context grows."""

from datetime import datetime, timezone

from app.modules.conversation_memory.contract import MemorySummary, WorkingMemoryState


class RollingSummaryBuilder:
    def __init__(self, *, trigger_messages: int = 8, max_chars: int = 2400) -> None:
        self.trigger_messages = trigger_messages
        self.max_chars = max_chars

    def build(
        self,
        memory: WorkingMemoryState,
        messages: list[str],
        *,
        source_turn_start: int,
    ) -> MemorySummary | None:
        if len(messages) < self.trigger_messages:
            return None
        facts = []
        if memory.destination:
            facts.append(f"điểm đến={memory.destination}")
        if memory.duration_days:
            facts.append(f"số ngày={memory.duration_days}")
        if memory.selected_places:
            facts.append("địa điểm đã chọn=" + ", ".join(memory.selected_places[:8]))
        excerpts = [" ".join(message.strip().split())[:220] for message in messages[-8:] if message.strip()]
        text = "; ".join([*facts, *excerpts])[: self.max_chars]
        return MemorySummary(
            summary_id=f"summary-{memory.chat_id}-{memory.version + 1}",
            text=text or "Không có thông tin hội thoại đáng lưu.",
            turns_covered=len(messages),
            key_facts_summary=facts,
            source_turn_start=source_turn_start,
            source_turn_end=source_turn_start + len(messages) - 1,
            version=memory.version + 1,
            provider="rule_based",
            model="rolling-v1",
            created_at=datetime.now(timezone.utc),
        )
