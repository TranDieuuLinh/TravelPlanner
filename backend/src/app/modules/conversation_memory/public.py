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
from app.modules.conversation_memory.summary import RollingSummaryBuilder
import asyncio
import logging
import asyncpg
from typing import Any
from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.adapters.in_memory import InMemoryMemoryRepository
from app.modules.conversation_memory.adapters.llm_reference_resolver import (
    HybridLlmReferenceResolver,
)
from app.shared.llm import GeminiLlmClient

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
                        self.database_url,
                        min_size=0,
                        max_size=1,
                        # Cloud Postgres providers may close idle TLS
                        # connections before the client notices. Recycling
                        # them sooner prevents stale connections from being
                        # handed to memory requests.
                        max_inactive_connection_lifetime=45,
                        timeout=5,
                        command_timeout=15,
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

    async def load_user_preferences(self, user_id):
        repo = await self._get_repo()
        return await repo.load_user_preferences(user_id)

    async def delete_user_preferences(self, user_id):
        repo = await self._get_repo()
        return await repo.delete_user_preferences(user_id)

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

    resolver = RuleBasedReferenceResolver()
    if (
        settings
        and getattr(settings, "conversation_memory_reference_provider", "rules") == "gemini"
        and getattr(settings, "gemini_api_key", None)
    ):
        resolver = HybridLlmReferenceResolver(
            GeminiLlmClient(
                settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
                key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
            ),
            fallback=resolver,
            confidence_threshold=settings.conversation_memory_reference_confidence,
            max_output_tokens=settings.conversation_memory_reference_max_output_tokens,
        )

    return ConversationMemoryService(
        repository=repository,
        extractor=RuleBasedFactExtractor(),
        resolver=resolver,
    )


__all__ = [
    "ConversationMemoryService",
    "FactExtractor",
    "FactProvenance",
    "FactScope",
    "FactStatus",
    "FactType",
    "InMemoryMemoryRepository",
    "HybridLlmReferenceResolver",
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
    "RollingSummaryBuilder",
    "UserPreferenceMemory",
    "WorkingMemoryState",
    "build_conversation_memory_service",
]
