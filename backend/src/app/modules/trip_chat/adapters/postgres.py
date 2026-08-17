import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.trip_chat.contract import (
    AccommodationUpdateStatus,
    PlanNoteUpdateStatus,
    TransportSelectionStatus,
    TripChat,
    TripChatMessage,
    TripChatSummary,
)
from app.modules.trip_chat.plan_snapshot import (
    delete_accommodation,
    select_transport_option,
    update_accommodation,
    update_stop_personal_notes,
)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _db_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


class PostgresTripChatRepository:
    """Repository for the agent_trip_chats tables from migration 003."""

    def __init__(self, database_url: str, *, command_timeout: float = 30.0) -> None:
        self.database_url = _db_url(database_url)
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg  # type: ignore[import-untyped]

            self._pool = await asyncpg.create_pool(
                self.database_url,
                command_timeout=self.command_timeout,
                min_size=1,
                max_size=10,
                max_inactive_connection_lifetime=45,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def create_chat(self, user_id: int, title: str | None) -> TripChat:
        chat_id, thread_id = str(uuid4()), str(uuid4())
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO agent_trip_chats (id, user_id, thread_id, title)
                   VALUES ($1, $2, $3, $4)""",
                chat_id,
                user_id,
                thread_id,
                (title or "Chuyến đi mới").strip()[:160],
            )
        return await self.get_chat(user_id, chat_id)  # type: ignore[return-value]

    async def list_chats(
        self, user_id: int, *, limit: int = 30, offset: int = 0
    ) -> list[TripChatSummary]:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT id, title, revision,
                          (current_itinerary IS NOT NULL OR
                           current_planner_output IS NOT NULL) AS has_itinerary,
                          created_at, updated_at
                   FROM agent_trip_chats
                   WHERE user_id=$1
                   ORDER BY updated_at DESC
                   LIMIT $2 OFFSET $3""",
                user_id,
                limit,
                offset,
            )
        return [self._summary(row) for row in rows]

    async def get_chat(self, user_id: int, chat_id: str) -> TripChat | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            chat = await connection.fetchrow(
                "SELECT * FROM agent_trip_chats WHERE id=$1 AND user_id=$2",
                chat_id,
                user_id,
            )
            if not chat:
                return None
            messages = await connection.fetch(
                """SELECT id, role, content, route, clarification_question, warnings,
                          sources, created_at
                   FROM agent_trip_chat_messages WHERE chat_id=$1 ORDER BY sequence""",
                chat_id,
            )
        return TripChat(
            **self._summary_values(chat),
            thread_id=chat["thread_id"],
            current_itinerary=_json(chat["current_itinerary"]),
            current_planner_output=_json(chat["current_planner_output"]),
            messages=[self._message(row) for row in messages],
        )

    async def append_exchange(
        self,
        user_id: int,
        chat_id: str,
        user_content: str,
        assistant: dict[str, Any],
        itinerary: dict[str, Any] | None,
        planner_output: dict[str, Any] | None,
    ) -> TripChat | None:
        pool = await self._get_pool()
        now = datetime.now(timezone.utc)
        async with pool.acquire() as connection:
            async with connection.transaction():
                chat = await connection.fetchrow(
                    """SELECT revision FROM agent_trip_chats
                       WHERE id=$1 AND user_id=$2 FOR UPDATE""",
                    chat_id,
                    user_id,
                )
                if not chat:
                    return None
                sequence = await connection.fetchval(
                    """SELECT COALESCE(MAX(sequence), 0)
                       FROM agent_trip_chat_messages WHERE chat_id=$1""",
                    chat_id,
                )
                await connection.execute(
                    """INSERT INTO agent_trip_chat_messages
                       (id, chat_id, sequence, role, content, created_at,
                        route, clarification_question, warnings, sources)
                       VALUES ($1,$2,$3,'user',$4,$5,NULL,NULL,'[]'::jsonb,'[]'::jsonb),
                              ($6,$2,$3+1,'assistant',$7,$5,$8,$9,$10::jsonb,$11::jsonb)""",
                    str(uuid4()),
                    chat_id,
                    sequence + 1,
                    user_content,
                    now,
                    str(uuid4()),
                    assistant["content"],
                    assistant.get("route"),
                    assistant.get("clarification_question"),
                    json.dumps(assistant.get("warnings", [])),
                    json.dumps(assistant.get("sources", [])),
                )
                await connection.execute(
                    """UPDATE agent_trip_chats SET revision=revision+1,
                       current_itinerary=COALESCE($1::jsonb, current_itinerary),
                       current_planner_output=COALESCE(
                           $2::jsonb, current_planner_output
                       ),
                       updated_at=$3
                       WHERE id=$4 AND user_id=$5""",
                    json.dumps(itinerary) if itinerary is not None else None,
                    json.dumps(planner_output) if planner_output is not None else None,
                    now,
                    chat_id,
                    user_id,
                )
        return await self.get_chat(user_id, chat_id)

    async def delete_chat(self, user_id: int, chat_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM agent_trip_chats WHERE id=$1 AND user_id=$2",
                chat_id,
                user_id,
            )
            return result.endswith("1")

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
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT revision, current_planner_output
                       FROM agent_trip_chats
                       WHERE id=$1 AND user_id=$2 FOR UPDATE""",
                    chat_id,
                    user_id,
                )
                if row is None:
                    return "chat_not_found"
                if row["revision"] != expected_revision:
                    return "revision_conflict"
                output = deepcopy(_json(row["current_planner_output"]))
                if not update_stop_personal_notes(
                    output,
                    day=day,
                    item_id=item_id,
                    personal_notes=personal_notes,
                ):
                    return "item_not_found"
                await connection.execute(
                    """UPDATE agent_trip_chats
                       SET revision=revision+1,
                           current_planner_output=$1::jsonb,
                           updated_at=$2
                       WHERE id=$3 AND user_id=$4""",
                    json.dumps(output),
                    datetime.now(timezone.utc),
                    chat_id,
                    user_id,
                )
        return "updated"

    async def update_accommodation(
        self,
        user_id: int,
        chat_id: str,
        *,
        expected_revision: int,
        changes: dict[str, Any] | None,
        delete: bool = False,
    ) -> AccommodationUpdateStatus:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT revision, current_planner_output
                       FROM agent_trip_chats
                       WHERE id=$1 AND user_id=$2 FOR UPDATE""",
                    chat_id,
                    user_id,
                )
                if row is None:
                    return "chat_not_found"
                if row["revision"] != expected_revision:
                    return "revision_conflict"
                output = deepcopy(_json(row["current_planner_output"]))
                changed = (
                    delete_accommodation(output)
                    if delete
                    else update_accommodation(output, changes=changes or {})
                )
                if not changed:
                    return "accommodation_not_found"
                await connection.execute(
                    """UPDATE agent_trip_chats
                       SET revision=revision+1,
                           current_planner_output=$1::jsonb,
                           updated_at=$2
                       WHERE id=$3 AND user_id=$4""",
                    json.dumps(output),
                    datetime.now(timezone.utc),
                    chat_id,
                    user_id,
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
        selection: dict[str, Any],
    ) -> TransportSelectionStatus:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT revision, current_planner_output
                       FROM agent_trip_chats
                       WHERE id=$1 AND user_id=$2 FOR UPDATE""",
                    chat_id,
                    user_id,
                )
                if row is None:
                    return "chat_not_found"
                if row["revision"] != expected_revision:
                    return "revision_conflict"
                output = deepcopy(_json(row["current_planner_output"]))
                status = select_transport_option(
                    output,
                    day=day,
                    leg_index=leg_index,
                    selection=selection,
                )
                if status != "updated":
                    return status
                await connection.execute(
                    """UPDATE agent_trip_chats
                       SET revision=revision+1,
                           current_planner_output=$1::jsonb,
                           updated_at=$2
                       WHERE id=$3 AND user_id=$4""",
                    json.dumps(output),
                    datetime.now(timezone.utc),
                    chat_id,
                    user_id,
                )
        return "updated"

    async def delete_all_chats(self, user_id: int) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM agent_trip_chats WHERE user_id=$1", user_id)

    @staticmethod
    def _summary_values(row) -> dict[str, Any]:
        has_itinerary = (
            row["has_itinerary"]
            if "has_itinerary" in row.keys()
            else (
                row["current_itinerary"] is not None
                or row["current_planner_output"] is not None
            )
        )
        return {
            "id": row["id"],
            "title": row["title"],
            "revision": row["revision"],
            "has_itinerary": has_itinerary,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @classmethod
    def _summary(cls, row) -> TripChatSummary:
        return TripChatSummary(**cls._summary_values(row))

    @staticmethod
    def _message(row) -> TripChatMessage:
        return TripChatMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            route=row["route"],
            clarification_question=row["clarification_question"],
            warnings=_json(row["warnings"]) or [],
            sources=_json(row["sources"]) or [],
            created_at=row["created_at"],
        )
