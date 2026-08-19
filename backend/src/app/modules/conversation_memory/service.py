"""Core domain service for Conversation Memory module."""

from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
    UserPreferenceMemory,
)
from app.modules.conversation_memory.extractor import RuleBasedFactExtractor
from app.modules.conversation_memory.merge_policy import MergePolicyEvaluator
from app.modules.conversation_memory.ports import (
    FactExtractor,
    MemoryRepository,
    ReferenceResolver,
)
from app.modules.conversation_memory.resolver import RuleBasedReferenceResolver
from app.modules.conversation_memory.summary import RollingSummaryBuilder


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
        self.summary_builder = RollingSummaryBuilder()

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
        recent_messages: Sequence[str] | None = None,
    ) -> tuple[Sequence[MemoryReference], bool]:
        """Resolve linguistic references in a user message against working memory."""
        return await self.resolver.resolve_references(
            message=message,
            current_memory=current_memory,
            recent_messages=recent_messages,
        )

    def merge_extracted_facts(
        self,
        current_memory: WorkingMemoryState,
        extracted_facts: Sequence[MemoryFact],
    ) -> WorkingMemoryState:
        """Merge extracted facts into WorkingMemoryState following conflict policies."""
        valid_facts = self.merge_policy.evaluate_facts(current_memory, extracted_facts)
        return self.merge_policy.merge_facts_into_memory_state(current_memory, valid_facts)

    def merge_facts_for_persistence(
        self,
        current_memory: WorkingMemoryState,
        extracted_facts: Sequence[MemoryFact],
    ) -> tuple[WorkingMemoryState, list[MemoryFact]]:
        """Merge facts and return only facts accepted for atomic persistence."""
        valid_facts = self.merge_policy.evaluate_facts(current_memory, extracted_facts)
        return (
            self.merge_policy.merge_facts_into_memory_state(current_memory, valid_facts),
            valid_facts,
        )

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
        recent_messages: Sequence[str] | None = None,
    ) -> tuple[WorkingMemoryState, Sequence[MemoryFact], Sequence[MemoryReference], bool]:
        """Extract facts, resolve references, and evaluate merge policies without persisting."""
        current = initial_memory if initial_memory is not None else await self.load_context(chat_id, user_id)
        extracted_facts = await self.extract_facts(message, current, turn=turn, message_id=message_id)
        references, clarification_required = await self.resolve_references(
            message, current, recent_messages=recent_messages
        )

        valid_facts = self.merge_policy.evaluate_facts(current, extracted_facts)
        merged_state = self.merge_policy.merge_facts_into_memory_state(current, valid_facts)

        if references or clarification_required:
            ref_list = [*merged_state.active_references, *references][-20:]
            goal = (
                "clarify_reference"
                if clarification_required
                else (None if references else merged_state.pending_goal)
            )
            merged_state = merged_state.model_copy(
                update={"active_references": ref_list, "pending_goal": goal}
            )
        elif merged_state.pending_goal == "clarify_reference":
            # A new ordinary user turn supersedes a stale clarification state;
            # otherwise every later request is incorrectly blocked as ambiguous.
            merged_state = merged_state.model_copy(update={"pending_goal": None})

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

    async def load_user_preferences(self, user_id: int) -> UserPreferenceMemory:
        """Read only explicitly confirmed, user-scoped facts."""
        return await self.repository.load_user_preferences(user_id)

    async def remember_user_facts(
        self,
        chat_id: str,
        user_id: int,
        facts: Sequence[MemoryFact],
    ) -> WorkingMemoryState:
        """Persist an explicit user preference; inferred chat facts are rejected."""
        explicit = [
            fact.model_copy(update={"scope": "user"})
            for fact in facts
            if fact.confirmed_by_user and fact.status == "active"
        ]
        if not explicit:
            return await self.load_context(chat_id, user_id)
        return await self.append_facts(chat_id, user_id, explicit)

    async def delete_user_preferences(self, user_id: int) -> int:
        return await self.repository.delete_user_preferences(user_id)

    def build_summary(
        self,
        memory: WorkingMemoryState,
        messages: list[str],
        *,
        source_turn_start: int,
    ):
        return self.summary_builder.build(
            memory, messages, source_turn_start=source_turn_start
        )
