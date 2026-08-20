from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.modules.conversation_memory.public import (
    ConversationMemoryService,
    FactProvenance,
    MemoryFact,
    MemoryVersionConflict,
)
from app.modules.trip_chat.contract import (
    AccommodationUpdateStatus,
    PlanNoteUpdateStatus,
    TransportSelectionStatus,
    PlanItemMutationStatus,
    TripChat,
    TripChatBootstrap,
)
from app.modules.trip_chat.ports import TripChatRepository
from app.modules.trip_chat.db_retry import (
    is_transient_database_error,
    retry_transient_database,
)

logger = logging.getLogger(__name__)


def _dump(value: Any, *, by_alias: bool = False) -> Any:
    return (
        value.model_dump(mode="json", by_alias=by_alias)
        if hasattr(value, "model_dump")
        else value
    )


class TripChatService:
    def __init__(
        self,
        repository: TripChatRepository,
        graph,
        memory_service: ConversationMemoryService | None = None,
    ) -> None:
        self.repository = repository
        self.graph = graph
        self.memory_service = memory_service

    async def create(self, user_id: int, title: str | None) -> TripChat:
        return await self.repository.create_chat(user_id, title)

    async def list(self, user_id: int, *, limit: int = 30, offset: int = 0):
        return await self.repository.list_chats(user_id, limit=limit, offset=offset)

    async def bootstrap(
        self, user_id: int, *, chat_id: str | None = None, limit: int = 30
    ) -> TripChatBootstrap:
        chats = await self.repository.list_chats(user_id, limit=limit)
        selected_id = chat_id or (chats[0].id if chats else None)
        active_chat = (
            await self.repository.get_chat(user_id, selected_id)
            if selected_id
            else None
        )
        return TripChatBootstrap(chats=chats, active_chat=active_chat)

    async def get(self, user_id: int, chat_id: str) -> TripChat | None:
        return await self.repository.get_chat(user_id, chat_id)

    async def update_personal_notes(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        item_id: str,
        personal_notes: str | None,
    ) -> tuple[PlanNoteUpdateStatus, TripChat | None]:
        normalized = personal_notes.strip() if personal_notes else None
        status = await self.repository.update_personal_notes(
            user_id,
            chat_id,
            expected_revision=expected_revision,
            day=day,
            item_id=item_id,
            personal_notes=normalized,
        )
        chat = (
            await self.repository.get_chat(user_id, chat_id)
            if status == "updated"
            else None
        )
        return status, chat

    async def update_accommodation(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        changes: dict[str, Any] | None,
        delete: bool = False,
    ) -> tuple[AccommodationUpdateStatus, TripChat | None]:
        normalized = dict(changes or {})
        for key in ("name", "address", "personalNotes"):
            if isinstance(normalized.get(key), str):
                normalized[key] = normalized[key].strip() or None
        status = await self.repository.update_accommodation(
            user_id,
            chat_id,
            expected_revision=expected_revision,
            changes=normalized,
            delete=delete,
        )
        chat = (
            await self.repository.get_chat(user_id, chat_id)
            if status == "updated"
            else None
        )
        return status, chat

    async def select_transport_option(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        leg_index: int,
        selection: dict[str, Any],
    ) -> tuple[TransportSelectionStatus, TripChat | None]:
        status = await self.repository.select_transport_option(
            user_id,
            chat_id,
            expected_revision=expected_revision,
            day=day,
            leg_index=leg_index,
            selection=selection,
        )
        chat = (
            await self.repository.get_chat(user_id, chat_id)
            if status == "updated"
            else None
        )
        return status, chat

    async def add_plan_item(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item: dict[str, Any], position: int | None = None,
    ) -> tuple[PlanItemMutationStatus, TripChat | None]:
        status = await self.repository.add_plan_item(
            user_id, chat_id, expected_revision=expected_revision,
            day=day, item=item, position=position,
        )
        chat = (
            await retry_transient_database(
                lambda: self.repository.get_chat(user_id, chat_id)
            )
            if status == "updated"
            else None
        )
        return status, chat

    async def confirm_unscheduled_place(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        name: str, place_id: str | None, candidate_id: str | None,
        day: int, item: dict[str, Any], position: int | None = None,
    ) -> tuple[PlanItemMutationStatus, TripChat | None]:
        status = await self.repository.confirm_unscheduled_place(
            user_id,
            chat_id,
            expected_revision=expected_revision,
            name=name,
            place_id=place_id,
            candidate_id=candidate_id,
            day=day,
            item=item,
            position=position,
        )
        chat = (
            await retry_transient_database(lambda: self.repository.get_chat(user_id, chat_id))
            if status == "updated"
            else None
        )
        return status, chat

    async def remove_unscheduled_place(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        name: str, place_id: str | None, candidate_id: str | None,
    ) -> tuple[PlanItemMutationStatus, TripChat | None]:
        status = await self.repository.remove_unscheduled_place(
            user_id,
            chat_id,
            expected_revision=expected_revision,
            name=name,
            place_id=place_id,
            candidate_id=candidate_id,
        )
        chat = (
            await retry_transient_database(lambda: self.repository.get_chat(user_id, chat_id))
            if status == "updated"
            else None
        )
        return status, chat

    async def reorder_plan_items(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item_ids: list[str],
    ) -> tuple[PlanItemMutationStatus, TripChat | None]:
        # The cloud connection can be dropped before the transaction starts.
        # Reorder is safe to retry: the expected revision makes a post-commit
        # retry return a conflict instead of applying the move twice.
        status = await retry_transient_database(
            lambda: self.repository.reorder_plan_items(
                user_id,
                chat_id,
                expected_revision=expected_revision,
                day=day,
                item_ids=item_ids,
            )
        )
        chat = (
            await retry_transient_database(
                lambda: self.repository.get_chat(user_id, chat_id)
            )
            if status == "updated"
            else None
        )
        return status, chat

    async def send(
        self,
        user_id: int,
        chat_id: str,
        content: str,
        graph_config: dict[str, Any] | None = None,
    ) -> TripChat | None:
        chat = await retry_transient_database(
            lambda: self.repository.get_chat(user_id, chat_id)
        )
        if not chat:
            return None

        recent_messages: list[str] = [
            f"{'User' if message.role == 'user' else 'Assistant'}: {message.content}"
            for message in chat.messages[-6:]
        ]
        max_retries = 3
        memory_warning = None
        result = None
        memory_version_before = None
        memory_version_after = None
        memory_facts_added = 0
        memory_reference_count = 0
        started_at = perf_counter()

        for attempt in range(max_retries):
            working_memory = None
            conversation_summary = None
            references = []
            valid_facts = []

            if self.memory_service is not None:
                try:
                    loaded_memory = await self.memory_service.load_context(chat_id, user_id)
                    memory_version_before = loaded_memory.version
                    bootstrap_facts = []
                    initial_memory = loaded_memory
                    load_preferences = getattr(self.memory_service, "load_user_preferences", None)
                    user_preferences = (
                        await load_preferences(user_id)
                        if load_preferences is not None
                        else None
                    )
                    if user_preferences and (
                        user_preferences.preferences or user_preferences.budget_tier
                    ):
                        initial_memory = initial_memory.model_copy(
                            update={
                                "preferences": list(
                                    dict.fromkeys(
                                        [*initial_memory.preferences, *user_preferences.preferences]
                                    )
                                ),
                                "budget": initial_memory.budget
                                or user_preferences.budget_tier,
                            }
                        )
                    if not loaded_memory.destination or not loaded_memory.mentioned_places:
                        bootstrap_facts = self._get_bootstrap_facts(chat)
                        for history_index, history_message in enumerate(chat.messages):
                            if history_message.role != "user":
                                continue
                            recovered = await self.memory_service.extract_facts(
                                history_message.content,
                                initial_memory,
                                turn=history_index // 2 + 1,
                                message_id=f"history:{history_message.id}",
                            )
                            bootstrap_facts.extend(recovered)
                            if recovered:
                                initial_memory = self.memory_service.merge_extracted_facts(
                                    initial_memory, recovered
                                )
                        if bootstrap_facts:
                            initial_memory = self.memory_service.merge_extracted_facts(
                                loaded_memory, bootstrap_facts
                            )

                    turn = len(chat.messages) // 2 + 1
                    (
                        working_memory,
                        user_facts,
                        references,
                        _clarification_req,
                    ) = await self.memory_service.prepare_message_context(
                        chat_id=chat_id,
                        user_id=user_id,
                        message=content,
                        turn=turn,
                        message_id=f"user:{chat_id}:{chat.revision + 1}",
                        initial_memory=initial_memory,
                        recent_messages=recent_messages,
                    )
                    rolling_summary = self.memory_service.build_summary(
                        working_memory,
                        [*recent_messages, content],
                        source_turn_start=max(1, len(chat.messages) // 2 - len(recent_messages) // 2 + 1),
                    )
                    if rolling_summary is not None:
                        working_memory = working_memory.model_copy(
                            update={"summary": rolling_summary.text}
                        )
                    valid_facts = list(bootstrap_facts) + list(user_facts)
                    memory_facts_added = len(valid_facts)
                    memory_reference_count = len(references)
                    conversation_summary = working_memory.summary
                except Exception as exc:
                    if is_transient_database_error(exc):
                        logger.warning(
                            "conversation_memory_transient_db_error chat_id=%s attempt=%d/%d error=%s",
                            chat_id,
                            attempt + 1,
                            max_retries,
                            type(exc).__name__,
                        )
                        if attempt < max_retries - 1:
                            continue
                    memory_warning = "Memory service error; falling back to transcript-only."
                    logger.exception(
                        "conversation_memory_prepare_failed chat_id=%s error=%s",
                        chat_id,
                        type(exc).__name__,
                    )
                    working_memory = None
                    valid_facts = []

            config = {"configurable": {"thread_id": chat.thread_id}}
            if graph_config:
                config.update(graph_config)

            graph_input = {
                "request_id": chat_id,
                "message": content,
                "supplied_candidates": [],
                "existing_itinerary": chat.current_itinerary,
                "edit_operation": None,
                "conversation_memory": working_memory,
                "recent_messages": recent_messages,
                "conversation_summary": conversation_summary,
                "resolved_references": references,
            }

            result = await self.graph.ainvoke(graph_input, config=config)

            if self.memory_service is not None and working_memory is not None:
                try:
                    information_output = result.get("information_output")
                    assistant_facts = []
                    if information_output and information_output.answer:
                        extracted = await self.memory_service.extract_facts(
                            information_output.answer,
                            working_memory,
                            turn=len(chat.messages) // 2 + 1,
                            message_id=f"assistant:{chat_id}:{chat.revision + 1}",
                        )
                        assistant_facts = [
                            fact.model_copy(
                                update={
                                    "confirmed_by_user": False,
                                    "provenance": fact.provenance.model_copy(
                                        update={
                                            "extracted_by": "information_finder_v1",
                                            "confidence": min(
                                                fact.provenance.confidence, 0.7
                                            ),
                                        }
                                    ),
                                }
                            )
                            for fact in extracted
                            if fact.fact_type == "place_candidate"
                        ]
                    if assistant_facts:
                        (
                            working_memory,
                            accepted_assistant_facts,
                        ) = self.memory_service.merge_facts_for_persistence(
                            working_memory, assistant_facts
                        )
                        valid_facts.extend(accepted_assistant_facts)
                        memory_facts_added = len(valid_facts)
                    await self.memory_service.persist_prepared_context(
                        memory=working_memory,
                        facts=valid_facts,
                        expected_version=working_memory.version,
                    )
                    memory_version_after = working_memory.version + 1
                    break  # Success
                except MemoryVersionConflict:
                    if attempt < max_retries - 1:
                        continue  # Retry pipeline
                    memory_warning = "Memory service error; version conflict after retries."
                    break
                except Exception as exc:
                    if is_transient_database_error(exc):
                        logger.warning(
                            "conversation_memory_persistence_transient_db_error chat_id=%s attempt=%d/%d error=%s",
                            chat_id,
                            attempt + 1,
                            max_retries,
                            type(exc).__name__,
                        )
                        if attempt < max_retries - 1:
                            continue
                    memory_warning = "Memory service error; memory persistence skipped."
                    logger.exception(
                        "conversation_memory_persistence_failed chat_id=%s error=%s",
                        chat_id,
                        type(exc).__name__,
                    )
                    break
            else:
                break  # No memory service, exit retry loop

        information_output = result.get("information_output")
        decision = result.get("decision")
        warnings = list(result.get("warnings", []))
        if memory_warning:
            warnings.append(memory_warning)

        assistant = {
            "content": result.get("response", "Request completed."),
            "route": getattr(decision, "route", None),
            "clarification_question": result.get("clarification_question"),
            "warnings": warnings,
            "content_blocks": [
                _dump(block, by_alias=True)
                for block in (
                    information_output.content_blocks if information_output else []
                )
            ],
            "sources": [
                _dump(source)
                for source in (
                    information_output.sources if information_output else []
                )
            ],
            "suggestions": (
                list(information_output.suggestions)
                if information_output and information_output.suggestions
                else list(result.get("suggestions", []))
            ),
        }

        logger.info(
            "trip_chat_memory_metrics",
            extra={
                "chat_id": chat_id,
                "memory_version_before": memory_version_before,
                "memory_version_after": memory_version_after,
                "facts_added": memory_facts_added,
                "reference_count": memory_reference_count,
                "route": getattr(decision, "route", None),
                "source_count": len(assistant["sources"]),
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "fallback_code": "memory_error" if memory_warning else None,
            },
        )

        return await retry_transient_database(
            lambda: self.repository.append_exchange(
                user_id,
                chat_id,
                content,
                assistant,
                _dump(result.get("itinerary")),
                _dump(result.get("planner_output"), by_alias=True),
            )
        )

    def _get_bootstrap_facts(self, chat: TripChat) -> list[MemoryFact]:
        dest = None
        dur = None
        if chat.current_itinerary:
            dest = getattr(chat.current_itinerary, "destination", None) or (
                chat.current_itinerary.get("destination")
                if isinstance(chat.current_itinerary, dict)
                else None
            )
            days = getattr(chat.current_itinerary, "days", None) or (
                chat.current_itinerary.get("days")
                if isinstance(chat.current_itinerary, dict)
                else None
            )
            if isinstance(days, list):
                dur = len(days)
        facts = []
        if dest:
            facts.append(
                MemoryFact(
                    fact_id=f"fact_dest_boot_{chat.id}",
                    fact_type="destination",
                    key="destination",
                    value=dest,
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="legacy_itinerary_bootstrap",
                        extracted_by="bootstrap",
                        confidence=0.8,
                    ),
                    confirmed_by_user=False,
                )
            )
        if dur:
            facts.append(
                MemoryFact(
                    fact_id=f"fact_dur_boot_{chat.id}",
                    fact_type="duration",
                    key="duration",
                    value=dur,
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="legacy_itinerary_bootstrap",
                        extracted_by="bootstrap",
                        confidence=0.8,
                    ),
                    confirmed_by_user=False,
                )
            )
        return facts
