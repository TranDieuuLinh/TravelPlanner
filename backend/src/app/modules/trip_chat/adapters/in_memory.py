"""In-memory adapter for TripChatRepository."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.trip_chat.contract import (
    AccommodationUpdateStatus,
    PlanNoteUpdateStatus,
    TransportSelectionStatus,
    PlanItemMutationStatus,
    TripChat,
    TripChatMessage,
)
from app.modules.trip_chat.plan_snapshot import (
    delete_accommodation,
    select_transport_option,
    add_plan_item,
    confirm_unscheduled_place,
    reorder_plan_items,
    remove_unscheduled_place,
    update_accommodation,
    update_stop_personal_notes,
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
            content_blocks=assistant.get("content_blocks", []),
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

    async def update_accommodation(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        changes: dict | None,
        delete: bool = False,
    ) -> AccommodationUpdateStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        changed = (
            delete_accommodation(output)
            if delete
            else update_accommodation(output, changes=changes or {})
        )
        if not changed:
            return "accommodation_not_found"
        self._chats[(user_id, chat_id)] = chat.model_copy(
            update={
                "revision": chat.revision + 1,
                "current_planner_output": output,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return "updated"

    async def select_transport_option(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        leg_index: int,
        selection: dict,
    ) -> TransportSelectionStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        status = select_transport_option(
            output,
            day=day,
            leg_index=leg_index,
            selection=selection,
        )
        if status != "updated":
            return status
        self._chats[(user_id, chat_id)] = chat.model_copy(
            update={
                "revision": chat.revision + 1,
                "current_planner_output": output,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return "updated"

    async def add_plan_item(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item: dict, position: int | None = None,
    ) -> PlanItemMutationStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        status = add_plan_item(output, day=day, item=item, position=position)
        if status != "updated":
            return status
        self._chats[(user_id, chat_id)] = chat.model_copy(update={
            "revision": chat.revision + 1,
            "current_planner_output": output,
            "has_itinerary": True,
            "updated_at": datetime.now(timezone.utc),
        })
        return "updated"

    async def confirm_unscheduled_place(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        name: str, place_id: str | None, candidate_id: str | None,
        day: int, item: dict, position: int | None = None,
    ) -> PlanItemMutationStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        status = confirm_unscheduled_place(
            output,
            name=name,
            place_id=place_id,
            candidate_id=candidate_id,
            day=day,
            item=item,
            position=position,
        )
        if status != "updated":
            return status
        self._chats[(user_id, chat_id)] = chat.model_copy(update={
            "revision": chat.revision + 1,
            "current_planner_output": output,
            "has_itinerary": True,
            "updated_at": datetime.now(timezone.utc),
        })
        return "updated"

    async def remove_unscheduled_place(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        name: str, place_id: str | None, candidate_id: str | None,
    ) -> PlanItemMutationStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        status = remove_unscheduled_place(
            output,
            name=name,
            place_id=place_id,
            candidate_id=candidate_id,
        )
        if status != "updated":
            return status
        self._chats[(user_id, chat_id)] = chat.model_copy(update={
            "revision": chat.revision + 1,
            "current_planner_output": output,
            "updated_at": datetime.now(timezone.utc),
        })
        return "updated"

    async def reorder_plan_items(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item_ids: list[str],
    ) -> PlanItemMutationStatus:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            return "chat_not_found"
        if chat.revision != expected_revision:
            return "revision_conflict"
        output = deepcopy(chat.current_planner_output)
        status = reorder_plan_items(output, day=day, item_ids=item_ids)
        if status != "updated":
            return status
        self._chats[(user_id, chat_id)] = chat.model_copy(update={
            "revision": chat.revision + 1,
            "current_planner_output": output,
            "updated_at": datetime.now(timezone.utc),
        })
        return "updated"
