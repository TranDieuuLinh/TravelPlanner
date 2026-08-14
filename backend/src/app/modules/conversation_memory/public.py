"""Public contract and service boundary for the Conversation Memory module."""

from app.modules.conversation_memory.contract import (
    FactProvenance,
    FactScope,
    FactStatus,
    FactType,
    MemoryFact,
    MemoryReference,
    MemorySummary,
    ReferenceType,
    RootStateMemoryMapping,
    UserPreferenceMemory,
    WorkingMemoryState,
)
from app.modules.conversation_memory.extractor import RuleBasedFactExtractor
from app.modules.conversation_memory.merge_policy import MergePolicyEvaluator
from app.modules.conversation_memory.ports import (
    FactExtractor,
    MemoryNotFound,
    MemoryPersistenceError,
    MemoryRepository,
    MemoryVersionConflict,
    ReferenceResolver,
)
from app.modules.conversation_memory.service import ConversationMemoryService
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver
import asyncio
import logging
import asyncpg
from typing import Any
from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.adapters.in_memory import InMemoryMemoryRepository

class LazyPostgresMemoryRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.pool = None
        self._repo = None
        self._init_lock = asyncio.Lock()

    async def _get_repo(self) -> PostgresMemoryRepository:
        if self._repo is None:
            async with self._init_lock:
                if self._repo is None:
                    self.pool = await asyncpg.create_pool(
                        self.database_url, min_size=1, max_size=10
                    )
                    self._repo = PostgresMemoryRepository(self.pool)
        return self._repo

    async def load_working_memory(self, chat_id: str, user_id: int):
        repo = await self._get_repo()
        return await repo.load_working_memory(chat_id, user_id)

    async def save_working_memory(self, memory, expected_version=None):
        repo = await self._get_repo()
        return await repo.save_working_memory(memory, expected_version)

    async def save_memory_and_facts(self, memory, facts=(), expected_version=None):
        repo = await self._get_repo()
        return await repo.save_memory_and_facts(memory, facts, expected_version)

    async def append_facts(self, chat_id, user_id, facts, expected_version=None):
        repo = await self._get_repo()
        return await repo.append_facts(chat_id, user_id, facts, expected_version)

    async def close(self):
        if self.pool:
            await self.pool.close()

def build_conversation_memory_service(
    settings: Any = None,
    repository: Any = None,
) -> ConversationMemoryService:
    if repository is None:
        if settings and getattr(settings, "database_url", None):
            repository = LazyPostgresMemoryRepository(settings.database_url)
            logging.info("Using PostgresMemoryRepository for conversation memory.")
        else:
            repository = InMemoryMemoryRepository()
            logging.warning("Using InMemoryMemoryRepository for conversation memory. Data will be lost on restart.")

    return ConversationMemoryService(
        repository=repository,
        extractor=RuleBasedFactExtractor(),
        resolver=RuleBasedReferenceResolver(),
    )


__all__ = [
    "ConversationMemoryService",
    "FactExtractor",
    "FactProvenance",
    "FactScope",
    "FactStatus",
    "FactType",
    "InMemoryMemoryRepository",
    "MemoryFact",
    "MemoryNotFound",
    "MemoryPersistenceError",
    "MemoryReference",
    "MemoryRepository",
    "MemorySummary",
    "MemoryVersionConflict",
    "MergePolicyEvaluator",
    "ReferenceResolver",
    "ReferenceType",
    "RootStateMemoryMapping",
    "RuleBasedFactExtractor",
    "RuleBasedReferenceResolver",
    "UserPreferenceMemory",
    "WorkingMemoryState",
    "build_conversation_memory_service",
]
