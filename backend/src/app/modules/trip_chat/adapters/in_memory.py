"""In-memory adapter for TripChatRepository."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.trip_chat.contract import (
    PlanNoteUpdateStatus,
    TripChat,
    TripChatMessage,
)
from app.modules.trip_chat.plan_snapshot import update_stop_personal_notes


class InMemoryTripChatRepository:
    """In-memory repository for TripChat testing."""

    def __init__(self) -> None:
        self._chats: dict[tuple[int, str], TripChat] = {}

    async def create_chat(self, user_id: int, title: str | None) -> TripChat:
        now = datetime.now(timezone.utc)
        chat_id = str(uuid4())
        chat = TripChat(
            id=chat_id,
            title=title or "Chuyến đi mới",
            user_id=user_id,
            thread_id=f"thread-{chat_id}",
            revision=1,
            has_itinerary=False,
            created_at=now,
            updated_at=now,
            messages=[],
        )
        self._chats[(user_id, chat_id)] = chat
        return chat

    async def list_chats(
        self, user_id: int, *, limit: int = 30, offset: int = 0
    ) -> list[TripChat]:
        chats = sorted(
            [chat for (uid, _), chat in self._chats.items() if uid == user_id],
            key=lambda chat: chat.updated_at,
            reverse=True,
        )
        return chats[offset : offset + limit]

    async def get_chat(self, user_id: int, chat_id: str) -> TripChat | None:
        return self._chats.get((user_id, chat_id))

    async def append_exchange(
        self,
        user_id: int,
        chat_id: str,
        user_content: str,
        assistant: dict,
        itinerary: dict | None = None,
        planner_output: dict | None = None,
    ) -> TripChat | None:
        chat = await self.get_chat(user_id, chat_id)
        if not chat:
            return None

        now = datetime.now(timezone.utc)
        user_msg = TripChatMessage(
            id=str(uuid4()),
            role="user",
            content=user_content,
            created_at=now,
        )

        assistant_msg = TripChatMessage(
            id=str(uuid4()),
            role="assistant",
            content=assistant.get("content", ""),
            route=assistant.get("route"),
            clarification_question=assistant.get("clarification_question"),
            warnings=assistant.get("warnings", []),
            sources=assistant.get("sources", []),
            created_at=now,
        )

        new_messages = list(chat.messages) + [user_msg, assistant_msg]
        new_itinerary = itinerary or chat.current_itinerary
        new_planner_output = planner_output or chat.current_planner_output

        updated_chat = chat.model_copy(
            update={
                "revision": chat.revision + 1,
                "has_itinerary": new_itinerary is not None or new_planner_output is not None,
                "messages": new_messages,
                "current_itinerary": new_itinerary,
                "current_planner_output": new_planner_output,
                "updated_at": now,
            }
        )
        self._chats[(user_id, chat_id)] = updated_chat
        return updated_chat

    async def update_personal_notes(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        item_id: str,
        personal_notes: str | None,
    ) -> PlanNoteUpdateStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        if not update_stop_personal_notes(
            output,
            day=day,
            item_id=item_id,
            personal_notes=personal_notes,
        ):
            return "item_not_found"
        self._chats[(user_id, chat_id)] = chat.model_copy(
            update={
                "revision": chat.revision + 1,
                "current_planner_output": output,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return "updated"
