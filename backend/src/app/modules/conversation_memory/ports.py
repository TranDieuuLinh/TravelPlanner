"""Port interfaces and exceptions for the Conversation Memory module."""

from typing import Protocol, Sequence

from app.modules.conversation_memory.contract import MemoryFact, WorkingMemoryState


class MemoryNotFound(Exception):
    """Raised when conversation working memory record is not found."""

    pass


class MemoryVersionConflict(Exception):
    """Raised when an optimistic concurrency version conflict occurs on save."""

    pass


class MemoryPersistenceError(Exception):
    """Raised when a generic persistence or data access error occurs."""

    pass


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
