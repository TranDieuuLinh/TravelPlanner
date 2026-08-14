from __future__ import annotations

from typing import Any

from app.modules.conversation_memory.public import (
    ConversationMemoryService,
    FactProvenance,
    MemoryFact,
    MemoryVersionConflict,
    WorkingMemoryState,
)
from app.modules.trip_chat.contract import TripChat
from app.modules.trip_chat.ports import TripChatRepository


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

    async def list(self, user_id: int):
        return await self.repository.list_chats(user_id)

    async def get(self, user_id: int, chat_id: str) -> TripChat | None:
        return await self.repository.get_chat(user_id, chat_id)

    async def send(
        self,
        user_id: int,
        chat_id: str,
        content: str,
        graph_config: dict[str, Any] | None = None,
    ) -> TripChat | None:
        chat = await self.repository.get_chat(user_id, chat_id)
        if not chat:
            return None

        recent_messages: list[str] = [m.content for m in chat.messages[-10:]]
        max_retries = 3
        memory_warning = None
        result = None

        for attempt in range(max_retries):
            working_memory = None
            conversation_summary = None
            references = []
            valid_facts = []

            if self.memory_service is not None:
                try:
                    loaded_memory = await self.memory_service.load_context(chat_id, user_id)
                    bootstrap_facts = []
                    initial_memory = loaded_memory
                    if loaded_memory.version == 0 and not loaded_memory.destination:
                        bootstrap_facts = self._get_bootstrap_facts(chat)
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
                        initial_memory=initial_memory,
                    )
                    valid_facts = list(bootstrap_facts) + list(user_facts)
                    conversation_summary = working_memory.summary
                except Exception as exc:
                    memory_warning = "Memory service error; falling back to transcript-only."
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
                    await self.memory_service.persist_prepared_context(
                        memory=working_memory,
                        facts=valid_facts,
                        expected_version=working_memory.version,
                    )
                    break  # Success
                except MemoryVersionConflict as version_exc:
                    if attempt < max_retries - 1:
                        continue  # Retry pipeline
                    memory_warning = "Memory service error; version conflict after retries."
                    break
                except Exception as exc:
                    memory_warning = "Memory service error; memory persistence skipped."
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
            "sources": [
                _dump(source)
                for source in (
                    information_output.sources if information_output else []
                )
            ],
        }

        return await self.repository.append_exchange(
            user_id,
            chat_id,
            content,
            assistant,
            _dump(result.get("itinerary")),
            _dump(result.get("planner_output"), by_alias=True),
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
