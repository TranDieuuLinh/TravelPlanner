"""Rule-based reference resolver implementation for Conversation Memory module."""

import uuid
from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.conversation_memory.extractor import remove_accents


class RuleBasedReferenceResolver:
    """Deterministic reference resolver for Vietnamese conversation references."""

    async def resolve_references(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        active_facts: Sequence[MemoryFact] | None = None,
    ) -> tuple[Sequence[MemoryReference], bool]:
        references: list[MemoryReference] = []
        clarification_required = False
        no_accent_msg = remove_accents(message)

        all_active = (
            active_facts
            if active_facts is not None
            else (current_memory.active_facts or current_memory.confirmed_facts)
        )
        place_facts = [
            f for f in all_active
            if f.key == "place_candidate" and f.status == "active"
        ]

        # 1. Deictic references ("các điểm bên trên", "những địa điểm trên")
        if any(kw in no_accent_msg for kw in ["cac diem ben tren", "nhung dia diem tren", "may cho o tren", "cac diem tren"]):
            phrase = "các điểm bên trên"
            if place_facts:
                resolved_places = [str(f.value) for f in place_facts]
                target_ids = [f.fact_id for f in place_facts]
            else:
                resolved_places = list(current_memory.mentioned_places)
                target_ids = []

            resolved_entity = ", ".join(resolved_places) if resolved_places else None

            references.append(
                MemoryReference(
                    reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                    phrase=phrase,
                    reference_type="deictic",
                    resolved_entity=resolved_entity,
                    target_fact_ids=target_ids,
                )
            )

        # 2. Anaphora references ("chỗ đó", "nó", "nơi đó", "địa điểm này")
        elif any(kw in no_accent_msg for kw in ["cho do", "no", "noi do", "dia diem nay"]):
            phrase = "chỗ đó"
            if place_facts:
                if len(place_facts) == 1:
                    target_fact = place_facts[0]
                    references.append(
                        MemoryReference(
                            reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                            phrase=phrase,
                            reference_type="anaphora",
                            resolved_entity=str(target_fact.value),
                            target_fact_ids=[target_fact.fact_id],
                        )
                    )
                else:
                    clarification_required = True
                    references.append(
                        MemoryReference(
                            reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                            phrase=phrase,
                            reference_type="anaphora",
                            resolved_entity=None,
                            target_fact_ids=[f.fact_id for f in place_facts],
                        )
                    )
            elif current_memory.mentioned_places:
                if len(current_memory.mentioned_places) == 1:
                    references.append(
                        MemoryReference(
                            reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                            phrase=phrase,
                            reference_type="anaphora",
                            resolved_entity=current_memory.mentioned_places[0],
                            target_fact_ids=[],
                        )
                    )
                else:
                    clarification_required = True
                    references.append(
                        MemoryReference(
                            reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                            phrase=phrase,
                            reference_type="anaphora",
                            resolved_entity=None,
                            target_fact_ids=[],
                        )
                    )

        # 3. Plan references ("lịch trình vừa rồi", "kế hoạch cũ", "plan vừa rồi")
        if any(kw in no_accent_msg for kw in ["lich trinh vua roi", "ke hoach cu", "plan vua roi", "lich trinh cu"]):
            phrase = "lịch trình vừa rồi"
            resolved_plan = current_memory.current_plan_ref
            references.append(
                MemoryReference(
                    reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                    phrase=phrase,
                    reference_type="plan_ref",
                    resolved_entity=resolved_plan,
                    target_fact_ids=[],
                )
            )

        return references, clarification_required
