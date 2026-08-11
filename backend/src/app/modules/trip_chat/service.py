from typing import Any

from app.modules.trip_chat.contract import TripChat
from app.modules.trip_chat.ports import TripChatRepository


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


class TripChatService:
    def __init__(self, repository: TripChatRepository, graph) -> None:
        self.repository = repository
        self.graph = graph

    async def create(self, user_id: int, title: str | None) -> TripChat:
        return await self.repository.create_chat(user_id, title)

    async def list(self, user_id: int):
        return await self.repository.list_chats(user_id)

    async def get(self, user_id: int, chat_id: str) -> TripChat | None:
        return await self.repository.get_chat(user_id, chat_id)

    async def send(self, user_id: int, chat_id: str, content: str) -> TripChat | None:
        chat = await self.repository.get_chat(user_id, chat_id)
        if not chat:
            return None
        result = await self.graph.ainvoke(
            {
                "request_id": chat_id,
                "message": content,
                "supplied_candidates": [],
                "existing_itinerary": chat.current_itinerary,
                "edit_operation": None,
            },
            config={"configurable": {"thread_id": chat.thread_id}},
        )
        information_output = result.get("information_output")
        decision = result.get("decision")
        assistant = {
            "content": result.get("response", "Request completed."),
            "route": getattr(decision, "route", None),
            "clarification_question": result.get("clarification_question"),
            "warnings": result.get("warnings", []),
            "sources": [
                _dump(source)
                for source in (information_output.sources if information_output else [])
            ],
        }
        return await self.repository.append_exchange(
            user_id,
            chat_id,
            content,
            assistant,
            _dump(result.get("itinerary")),
        )
