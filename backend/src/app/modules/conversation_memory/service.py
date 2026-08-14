"""Core domain service for Conversation Memory module."""

from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.conversation_memory.extractor import RuleBasedFactExtractor
from app.modules.conversation_memory.merge_policy import MergePolicyEvaluator
from app.modules.conversation_memory.ports import (
    FactExtractor,
    MemoryRepository,
    ReferenceResolver,
)
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver


class ConversationMemoryService:
    """Service providing core working memory load, save, fact extraction, reference resolution, and policy merge capabilities."""

    def __init__(
        self,
        repository: MemoryRepository,
        extractor: FactExtractor | None = None,
        resolver: ReferenceResolver | None = None,
    ) -> None:
        self.repository = repository
        self.extractor = extractor or RuleBasedFactExtractor()
        self.resolver = resolver or RuleBasedReferenceResolver()
        self.merge_policy = MergePolicyEvaluator()

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
            travelers=None,
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
            active_facts=[],
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

    async def extract_facts(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        turn: int = 1,
        message_id: str | None = None,
    ) -> Sequence[MemoryFact]:
        """Extract structured memory facts from a user message."""
        return await self.extractor.extract_facts(
            message=message,
            current_memory=current_memory,
            turn=turn,
            message_id=message_id,
        )

    async def resolve_references(
        self,
        message: str,
        current_memory: WorkingMemoryState,
    ) -> tuple[Sequence[MemoryReference], bool]:
        """Resolve linguistic references in a user message against working memory."""
        return await self.resolver.resolve_references(
            message=message,
            current_memory=current_memory,
        )

    def merge_extracted_facts(
        self,
        current_memory: WorkingMemoryState,
        extracted_facts: Sequence[MemoryFact],
    ) -> WorkingMemoryState:
        """Merge extracted facts into WorkingMemoryState following conflict policies."""
        valid_facts = self.merge_policy.evaluate_facts(current_memory, extracted_facts)
        return self.merge_policy.merge_facts_into_memory_state(current_memory, valid_facts)

    async def append_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
        expected_version: int | None = None,
    ) -> WorkingMemoryState:
        """Append memory facts enforcing merge policy rules and atomic persistence."""
        current = await self.load_context(chat_id, user_id)
        valid_facts = self.merge_policy.evaluate_facts(current, facts)

        if not valid_facts:
            return current

        effective_expected_version = (
            current.version if expected_version is None else expected_version
        )

        merged_state = self.merge_policy.merge_facts_into_memory_state(current, valid_facts)

        return await self.repository.save_memory_and_facts(
            memory=merged_state,
            facts=valid_facts,
            expected_version=effective_expected_version,
        )

    async def prepare_message_context(
        self,
        chat_id: str,
        user_id: int,
        message: str,
        turn: int = 1,
        message_id: str | None = None,
        initial_memory: WorkingMemoryState | None = None,
    ) -> tuple[WorkingMemoryState, Sequence[MemoryFact], Sequence[MemoryReference], bool]:
        """Extract facts, resolve references, and evaluate merge policies without persisting."""
        current = initial_memory if initial_memory is not None else await self.load_context(chat_id, user_id)
        extracted_facts = await self.extract_facts(message, current, turn=turn, message_id=message_id)
        references, clarification_required = await self.resolve_references(message, current)

        valid_facts = self.merge_policy.evaluate_facts(current, extracted_facts)
        merged_state = self.merge_policy.merge_facts_into_memory_state(current, valid_facts)

        if references or clarification_required:
            ref_list = list(merged_state.active_references) + list(references)
            goal = "clarify_reference" if clarification_required else merged_state.pending_goal
            merged_state = merged_state.model_copy(
                update={"active_references": ref_list, "pending_goal": goal}
            )

        return merged_state, valid_facts, references, clarification_required

    async def persist_prepared_context(
        self,
        memory: WorkingMemoryState,
        facts: Sequence[MemoryFact],
        expected_version: int,
    ) -> WorkingMemoryState:
        """Persist a prepared memory state and facts atomically."""
        return await self.repository.save_memory_and_facts(
            memory=memory,
            facts=facts,
            expected_version=expected_version,
        )
