from typing import Any, Protocol

from app.modules.trip_chat.contract import (
    PlanNoteUpdateStatus,
    TripChat,
    TripChatSummary,
)


class TripChatRepository(Protocol):
    async def create_chat(self, user_id: int, title: str | None) -> TripChat: ...

    async def list_chats(
        self, user_id: int, *, limit: int = 30, offset: int = 0
    ) -> list[TripChatSummary]: ...

    async def get_chat(self, user_id: int, chat_id: str) -> TripChat | None: ...

    async def append_exchange(
        self,
        user_id: int,
        chat_id: str,
        user_content: str,
        assistant: dict[str, Any],
        itinerary: dict[str, Any] | None,
        planner_output: dict[str, Any] | None,
    ) -> TripChat | None: ...

    async def update_personal_notes(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        item_id: str,
        personal_notes: str | None,
    ) -> PlanNoteUpdateStatus: ...

    async def delete_chat(self, user_id: int, chat_id: str) -> bool: ...

    async def delete_all_chats(self, user_id: int) -> None: ...
