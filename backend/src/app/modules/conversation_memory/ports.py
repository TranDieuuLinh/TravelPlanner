"""Port interfaces and exceptions for the Conversation Memory module."""

from typing import Protocol, Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
)


class MemoryNotFound(Exception):
    """Raised when conversation working memory record is not found."""

    pass


class MemoryVersionConflict(Exception):
    """Raised when an optimistic concurrency version conflict occurs on save."""

    pass


class MemoryPersistenceError(Exception):
    """Raised when a generic persistence or data access error occurs."""

    pass


class FactExtractor(Protocol):
    """Port interface for extracting structured memory facts from user messages."""

    async def extract_facts(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        recent_messages: Sequence[dict] | None = None,
        turn: int = 1,
        message_id: str | None = None,
    ) -> Sequence[MemoryFact]:
        ...


class ReferenceResolver(Protocol):
    """Port interface for resolving linguistic references (anaphora, deictics) in user messages."""

    async def resolve_references(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        active_facts: Sequence[MemoryFact] | None = None,
    ) -> tuple[Sequence[MemoryReference], bool]:
        """Resolves references in message against memory.

        Returns a tuple of (references, clarification_required).
        """
        ...


class MemoryRepository(Protocol):
    """Repository protocol interface for persisting and loading conversation working memory."""

    async def load_working_memory(
        self,
        chat_id: str,
        user_id: int,
    ) -> WorkingMemoryState | None:
        ...

    async def save_working_memory(
        self,
        memory: WorkingMemoryState,
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        ...

    async def append_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        ...

    async def save_memory_and_facts(
        self,
        memory: WorkingMemoryState,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        ...
