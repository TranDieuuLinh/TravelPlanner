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
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver
from app.modules.conversation_memory.service import ConversationMemoryService

__all__ = [
    "ConversationMemoryService",
    "FactExtractor",
    "FactProvenance",
    "FactScope",
    "FactStatus",
    "FactType",
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
]
