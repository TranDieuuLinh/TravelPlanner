import asyncio
import json

from app.modules.plan_editor.public import NaturalLanguagePlanEdit
from app.modules.trip_chat.adapters.postgres_plan_edit import (
    append_plan_edit_exchange,
)


class AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return None


class FakeConnection:
    def __init__(self):
        self.executions = []

    def transaction(self):
        return AsyncContext()

    async def fetchrow(self, _query, *_args):
        return {
            "revision": 4,
            "current_planner_output": {
                "days": [{
                    "day": 1,
                    "stops": [{
                        "itemId": "museum",
                        "name": "Bảo tàng",
                        "durationMinutes": 60,
                    }],
                }],
            },
        }

    async def fetchval(self, _query, *_args):
        return 2

    async def execute(self, query, *args):
        self.executions.append((query, args))
        return "OK"


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


def test_plan_mutation_and_exchange_share_one_revision_update() -> None:
    connection = FakeConnection()
    status = asyncio.run(
        append_plan_edit_exchange(
            FakePool(connection),
            7,
            "chat-1",
            expected_revision=4,
            user_content="Cho Bảo tàng 90 phút",
            assistant={"content": "Đã cập nhật.", "route": "plan_editor"},
            edit=NaturalLanguagePlanEdit(
                action="update",
                confidence=0.99,
                day=1,
                item_id="museum",
                item={"durationMinutes": 90},
            ),
        )
    )

    assert status == "updated"
    assert len(connection.executions) == 2
    insert_query, _insert_args = connection.executions[0]
    update_query, update_args = connection.executions[1]
    assert "INSERT INTO agent_trip_chat_messages" in insert_query
    assert "revision=revision+1" in update_query
    assert json.loads(update_args[0])["days"][0]["stops"][0]["durationMinutes"] == 90
