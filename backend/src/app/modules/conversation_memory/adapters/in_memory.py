"""In-memory adapter for Conversation Memory repository."""

from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    UserPreferenceMemory,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import MemoryVersionConflict


class InMemoryMemoryRepository:
    """In-memory implementation of MemoryRepository port for fallback and testing."""

    def __init__(self) -> None:
        self._memories: dict[str, WorkingMemoryState] = {}
        self._facts: dict[str, list[MemoryFact]] = {}

    async def load_working_memory(
        self, chat_id: str, user_id: int
    ) -> WorkingMemoryState | None:
        memory = self._memories.get(chat_id)
        if memory and memory.user_id == user_id:
            return memory
        return None

    async def save_working_memory(
        self, memory: WorkingMemoryState, expected_version: int | None = None
    ) -> WorkingMemoryState:
        existing = self._memories.get(memory.chat_id)
        if existing:
            current_ver = existing.version
            if expected_version is not None and expected_version != current_ver:
                raise MemoryVersionConflict(
                    f"Version conflict for chat {memory.chat_id}: expected {expected_version}, got {current_ver}"
                )
            new_version = current_ver + 1
        else:
            if expected_version is not None and expected_version != 0:
                raise MemoryVersionConflict(
                    f"Version conflict for new chat {memory.chat_id}: expected {expected_version}, got 0"
                )
            new_version = 1

        updated_memory = memory.model_copy(update={"version": new_version})
        self._memories[memory.chat_id] = updated_memory
        return updated_memory

    async def append_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        memory = await self.load_working_memory(chat_id, user_id)
        if not memory:
            memory = WorkingMemoryState(chat_id=chat_id, user_id=user_id, version=0)

        return await self.save_memory_and_facts(
            memory, facts=facts, expected_version=expected_version
        )

    async def save_memory_and_facts(
        self,
        memory: WorkingMemoryState,
        facts: Sequence[MemoryFact] = (),
        expected_version: int | None = None,
        new_facts: Sequence[MemoryFact] | None = None,
    ) -> WorkingMemoryState:
        incoming_facts = list(facts) if facts else list(new_facts or [])
        existing_facts = list(self._facts.get(memory.chat_id, []))
        updated_facts: list[MemoryFact] = []

        for ef in existing_facts:
            superseded = False
            for nf in incoming_facts:
                if ef.status != "active":
                    continue
                if ef.fact_type in ("destination", "duration", "travelers", "budget_tier"):
                    if ef.key == nf.key:
                        superseded = True
                        break
                elif ef.fact_type == "place_candidate":
                    if ef.key == nf.key and ef.normalized_value == nf.normalized_value:
                        superseded = True
                        break
            if superseded:
                updated_facts.append(ef.model_copy(update={"status": "superseded"}))
            else:
                updated_facts.append(ef)

        for nf in incoming_facts:
            updated_facts.append(nf)

        self._facts[memory.chat_id] = updated_facts

        # Compute active/confirmed lists for projection
        active_facts = [f for f in updated_facts if f.status == "active"]
        confirmed_facts = [f for f in active_facts if f.confirmed_by_user]

        projection = memory.model_copy(
            update={
                "active_facts": active_facts,
                "confirmed_facts": confirmed_facts,
            }
        )
        return await self.save_working_memory(projection, expected_version=expected_version)

    async def load_user_preferences(self, user_id: int) -> UserPreferenceMemory:
        facts = [
            fact for values in self._facts.values() for fact in values
            if fact.scope == "user" and fact.status == "active"
            and fact.confirmed_by_user
        ]
        preferences = [str(fact.value) for fact in facts if fact.fact_type == "travel_style"]
        dietary = [str(fact.value) for fact in facts if fact.key == "dietary_restriction"]
        budget = next(
            (str(fact.value) for fact in facts if fact.fact_type == "budget_tier"),
            None,
        )
        return UserPreferenceMemory(
            user_id=user_id,
            preferences=list(dict.fromkeys(preferences)),
            dietary_restrictions=list(dict.fromkeys(dietary)),
            budget_tier=budget,
            confidence=min((fact.provenance.confidence for fact in facts), default=1.0),
        )

    async def delete_user_preferences(self, user_id: int) -> int:
        deleted = 0
        for chat_id, values in list(self._facts.items()):
            updated = []
            for fact in values:
                if fact.scope == "user" and fact.status == "active":
                    updated.append(fact.model_copy(update={"status": "rejected"}))
                    deleted += 1
                else:
                    updated.append(fact)
            self._facts[chat_id] = updated
        return deleted
