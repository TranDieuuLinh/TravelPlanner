from typing import Any, Protocol

from app.modules.trip_chat.contract import TripChat, TripChatSummary


class TripChatRepository(Protocol):
    async def create_chat(self, user_id: int, title: str | None) -> TripChat: ...

    async def list_chats(self, user_id: int) -> list[TripChatSummary]: ...

    async def get_chat(self, user_id: int, chat_id: str) -> TripChat | None: ...

    async def append_exchange(
        self,
        user_id: int,
        chat_id: str,
        user_content: str,
        assistant: dict[str, Any],
        itinerary: dict[str, Any] | None,
    ) -> TripChat | None: ...

    async def delete_chat(self, user_id: int, chat_id: str) -> bool: ...

    async def delete_all_chats(self, user_id: int) -> None: ...
