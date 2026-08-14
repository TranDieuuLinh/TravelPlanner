"""In-memory adapter for TripChatRepository."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.trip_chat.contract import (
    TripChat,
    TripChatMessage,
)


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

    async def list_chats(self, user_id: int) -> list[TripChat]:
        return [chat for (uid, _), chat in self._chats.items() if uid == user_id]

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
