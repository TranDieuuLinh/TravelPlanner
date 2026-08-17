"""Hybrid semantic reference resolver backed by the shared LLM client."""

import json
import logging
import unicodedata
from typing import Literal, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.modules.conversation_memory.contract import (
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver
from app.shared.llm import LlmClient

logger = logging.getLogger(__name__)


def _provider_schema(value: object) -> object:
    """Remove JSON Schema defaults rejected by some Gemini endpoints."""
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value


class ReferenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["none", "single_place", "place_set", "plan"]
    phrase: str = Field(default="", max_length=200)
    target_fact_ids: list[str] = Field(default_factory=list, max_length=50)
    target_place_names: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(ge=0, le=1)
    clarification_required: bool = False


SYSTEM_PROMPT = """Bạn phân giải tham chiếu hội thoại cho TravelPlanner.
Chỉ trả JSON đúng schema. Dùng message, transcript gần đây và memory có cấu trúc.
Không được tạo fact ID mới; target_fact_ids chỉ được lấy từ candidateFacts.
Nếu địa điểm có trong transcript nhưng chưa có candidateFacts, trả đúng tên đã xuất
hiện qua target_place_names; không suy diễn địa điểm mới.

Quy tắc ngữ nghĩa:
- "những/các/mấy chỗ đó", "danh sách trên", "đi hết", "tất cả" thường là place_set.
- "chỗ đó", "nó", "nơi ấy" là single_place nếu ngữ cảnh chỉ rõ một địa điểm.
- "lịch trình cũ/vừa rồi" là plan.
- Nếu message không tham chiếu ngược, trả kind=none.
- Chỉ clarification_required=true khi thực sự có nhiều cách hiểu cạnh tranh.
- Với place_set, chọn mọi candidate fact thuộc tập được nhắc đến; không hỏi lại chỉ vì tập có nhiều phần tử.
"""


class HybridLlmReferenceResolver:
    """Use semantic resolution first and deterministic rules as safe fallback."""

    def __init__(
        self,
        client: LlmClient,
        *,
        fallback: RuleBasedReferenceResolver | None = None,
        confidence_threshold: float = 0.72,
        max_output_tokens: int = 320,
    ) -> None:
        self.client = client
        self.fallback = fallback or RuleBasedReferenceResolver()
        self.confidence_threshold = confidence_threshold
        self.max_output_tokens = max_output_tokens

    async def resolve_references(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        active_facts: Sequence[MemoryFact] | None = None,
        recent_messages: Sequence[str] | None = None,
    ) -> tuple[Sequence[MemoryReference], bool]:
        facts = list(active_facts or current_memory.active_facts)
        candidate_facts = [
            fact for fact in facts
            if fact.status == "active" and fact.key == "place_candidate"
        ]
        if (
            not candidate_facts
            and not current_memory.current_plan_ref
            and not recent_messages
        ):
            return await self.fallback.resolve_references(
                message, current_memory, active_facts, recent_messages
            )

        payload = {
            "message": message[-1000:],
            "recentMessages": [item[-500:] for item in (recent_messages or [])[-6:]],
            "summary": (current_memory.summary or "")[-1500:],
            "destination": current_memory.destination,
            "durationDays": current_memory.duration_days,
            "mentionedPlaces": current_memory.mentioned_places[-50:],
            "selectedPlaces": current_memory.selected_places[-50:],
            "currentPlanRef": current_memory.current_plan_ref,
            "candidateFacts": [
                {"factId": fact.fact_id, "value": str(fact.value)}
                for fact in candidate_facts[-50:]
            ],
        }
        try:
            raw = await self.client.generate(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                system_prompt=SYSTEM_PROMPT,
                temperature=0.0,
                max_output_tokens=self.max_output_tokens,
                response_json_schema=_provider_schema(
                    ReferenceDecision.model_json_schema()
                ),
            )
            decision = ReferenceDecision.model_validate_json(raw)
            resolved = self._validated_reference(
                decision,
                candidate_facts,
                current_memory,
                recent_messages or [],
            )
            if resolved is not None:
                return resolved
        except Exception as exc:
            logger.warning(
                "semantic_reference_resolution_fallback error=%s",
                type(exc).__name__,
            )
        return await self.fallback.resolve_references(
            message, current_memory, active_facts, recent_messages
        )

    def _validated_reference(
        self,
        decision: ReferenceDecision,
        candidates: Sequence[MemoryFact],
        memory: WorkingMemoryState,
        recent_messages: Sequence[str],
    ) -> tuple[list[MemoryReference], bool] | None:
        if decision.confidence < self.confidence_threshold:
            return None
        if decision.kind == "none":
            return [], False
        if decision.kind == "plan":
            if not memory.current_plan_ref:
                return None
            return [MemoryReference(
                reference_id=f"ref_{uuid4().hex[:12]}",
                phrase=decision.phrase or "lịch trình trước",
                reference_type="plan_ref",
                resolved_entity=memory.current_plan_ref,
            )], False

        by_id = {fact.fact_id: fact for fact in candidates}
        ids = list(dict.fromkeys(decision.target_fact_ids))
        if any(fact_id not in by_id for fact_id in ids):
            return None
        values = [str(by_id[fact_id].value) for fact_id in ids]
        evidence = " ".join(
            [
                *recent_messages,
                memory.summary or "",
                *memory.mentioned_places,
                *memory.selected_places,
            ]
        )
        normalized_evidence = self._normalize(evidence)
        for name in decision.target_place_names:
            clean_name = " ".join(name.split())[:200]
            if not clean_name or self._normalize(clean_name) not in normalized_evidence:
                return None
            if self._normalize(clean_name) not in {
                self._normalize(value) for value in values
            }:
                values.append(clean_name)
        if not values:
            return None
        if decision.kind == "single_place" and len(values) != 1:
            return None
        reference_type = "deictic" if decision.kind == "place_set" else "anaphora"
        return [MemoryReference(
            reference_id=f"ref_{uuid4().hex[:12]}",
            phrase=decision.phrase or "các địa điểm đã nhắc",
            reference_type=reference_type,
            resolved_entity=", ".join(values),
            target_fact_ids=ids,
        )], decision.clarification_required

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return " ".join(
            "".join(char for char in decomposed if not unicodedata.combining(char))
            .replace("đ", "d")
            .split()
        )
