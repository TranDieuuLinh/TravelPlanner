import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.plan_editor.public import NaturalLanguagePlanEdit
from app.modules.trip_chat.contract import PlanItemMutationStatus
from app.modules.trip_chat.plan_edit_execution import apply_plan_edit_to_output


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def append_plan_edit_exchange(
    pool,
    user_id: int,
    chat_id: str,
    *,
    expected_revision: int,
    user_content: str,
    assistant: dict[str, Any],
    edit: NaturalLanguagePlanEdit,
) -> PlanItemMutationStatus:
    """Atomically mutate the plan and append the visible chat exchange."""
    now = datetime.now(timezone.utc)
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
            status = apply_plan_edit_to_output(output, edit)
            if status != "updated":
                return status
            sequence = await connection.fetchval(
                """SELECT COALESCE(MAX(sequence), 0)
                   FROM agent_trip_chat_messages WHERE chat_id=$1""",
                chat_id,
            )
            await connection.execute(
                """INSERT INTO agent_trip_chat_messages
                   (id, chat_id, sequence, role, content, created_at,
                   route, clarification_question, warnings, content_blocks, sources, suggestions)
                   VALUES ($1,$2,$3,'user',$4,$5,NULL,NULL,'[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'[]'::jsonb),
                          ($6,$2,$3+1,'assistant',$7,$5,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb)""",
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
                json.dumps(assistant.get("content_blocks", [])),
                json.dumps(assistant.get("sources", [])),
                json.dumps(assistant.get("suggestions", [])),
            )
            await connection.execute(
                """UPDATE agent_trip_chats SET revision=revision+1,
                   current_planner_output=$1::jsonb, updated_at=$2
                   WHERE id=$3 AND user_id=$4""",
                json.dumps(output),
                now,
                chat_id,
                user_id,
            )
    return "updated"
