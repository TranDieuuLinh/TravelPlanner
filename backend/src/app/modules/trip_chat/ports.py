from typing import Any, Protocol

from app.modules.trip_chat.contract import (
    AccommodationUpdateStatus,
    PlanNoteUpdateStatus,
    TransportSelectionStatus,
    PlanItemMutationStatus,
    TripChat,
    TripChatSummary,
)


class DayPlanRepairer(Protocol):
    async def repair(
        self,
        output: dict[str, Any] | None,
        *,
        day: int,
        item_id: str,
        replacement: dict[str, Any],
    ) -> dict[str, Any]: ...


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

    async def update_accommodation(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        changes: dict[str, Any] | None,
        delete: bool = False,
    ) -> AccommodationUpdateStatus: ...

    async def select_transport_option(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        day: int,
        leg_index: int,
        selection: dict[str, Any],
    ) -> TransportSelectionStatus: ...

    async def add_plan_item(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item: dict[str, Any], position: int | None = None,
    ) -> PlanItemMutationStatus: ...

    async def update_plan_item(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item_id: str, changes: dict[str, Any],
    ) -> PlanItemMutationStatus: ...

    async def replace_plan_output(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        output: dict[str, Any],
    ) -> PlanItemMutationStatus: ...

    async def delete_plan_item(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item_id: str,
    ) -> PlanItemMutationStatus: ...

    async def confirm_unscheduled_place(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        name: str,
        place_id: str | None,
        candidate_id: str | None,
        day: int,
        item: dict[str, Any],
        position: int | None = None,
    ) -> PlanItemMutationStatus: ...

    async def remove_unscheduled_place(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        name: str,
        place_id: str | None,
        candidate_id: str | None,
    ) -> PlanItemMutationStatus: ...

    async def reorder_plan_items(
        self, user_id: int, chat_id: str, *, expected_revision: int,
        day: int, item_ids: list[str],
    ) -> PlanItemMutationStatus: ...

    async def delete_chat(self, user_id: int, chat_id: str) -> bool: ...

    async def delete_all_chats(self, user_id: int) -> None: ...
