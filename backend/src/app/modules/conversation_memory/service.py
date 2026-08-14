"""Core domain service for Conversation Memory module."""

from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import MemoryRepository


class ConversationMemoryService:
    """Service providing core working memory load, initialize, save, and fact append capabilities."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def initialize_empty_memory(
        self,
        chat_id: str,
        user_id: int,
    ) -> WorkingMemoryState:
        """Instantiate an initial empty WorkingMemoryState with version 0."""
        return WorkingMemoryState(
            chat_id=chat_id,
            user_id=user_id,
            destination=None,
            duration_days=None,
            budget=None,
            preferences=[],
            avoids=[],
            mentioned_places=[],
            selected_places=[],
            current_plan_ref=None,
            pending_goal=None,
            last_route=None,
            summary=None,
            version=0,
            confirmed_facts=[],
            active_references=[],
        )

    async def load_context(
        self,
        chat_id: str,
        user_id: int,
    ) -> WorkingMemoryState:
        """Load working memory for a chat session, returning an empty initial memory if none exists."""
        memory = await self.repository.load_working_memory(chat_id, user_id)
        if memory is None:
            return await self.initialize_empty_memory(chat_id, user_id)
        return memory

    async def save_working_memory(
        self,
        memory: WorkingMemoryState,
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        """Persist updated working memory state using optimistic concurrency control."""
        return await self.repository.save_working_memory(
            memory,
            expected_version=expected_version,
        )

    async def append_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        """Append memory facts enforcing merge policy rules:

        - Confirmed facts cannot be silently overwritten by unconfirmed low-confidence facts.
        - Selected places are distinct and not automatically generated from mentioned places.
        - Memory version increments atomically.
        """
        current = await self.load_context(chat_id, user_id)

        # Merge policy validation
        valid_facts: list[MemoryFact] = []
        for new_fact in facts:
            # Check existing confirmed facts with matching key
            existing_confirmed = [
                f for f in current.confirmed_facts
                if f.key == new_fact.key and f.confirmed_by_user
            ]
            if existing_confirmed and not new_fact.confirmed_by_user:
                # Unconfirmed fact cannot overwrite user-confirmed fact; skip or keep existing
                continue
            valid_facts.append(new_fact)

        if not valid_facts:
            return current

        effective_expected_version = (
            current.version if expected_version is None else expected_version
        )

        return await self.repository.append_facts(
            chat_id=chat_id,
            user_id=user_id,
            facts=valid_facts,
            expected_version=effective_expected_version,
        )
