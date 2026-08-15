import asyncio
import json
from datetime import datetime, timezone

from app.modules.trip_chat.adapters.postgres import PostgresTripChatRepository


class FakeConnection:
    def __init__(self) -> None:
        self.query = ""
        self.args = ()

    async def fetch(self, query, *args):
        self.query = query
        self.args = args
        now = datetime.now(timezone.utc)
        return [{
            "id": "chat-1",
            "title": "Hà Nội",
            "revision": 2,
            "has_itinerary": True,
            "created_at": now,
            "updated_at": now,
        }]


class AcquireContext:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return None


class FakePool:
    def __init__(self, connection) -> None:
        self.connection = connection

    def acquire(self):
        return AcquireContext(self.connection)


class TransactionContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_args):
        return None


class FakeMutationConnection:
    def __init__(self) -> None:
        self.updated_args = ()

    def transaction(self):
        return TransactionContext()

    async def fetchrow(self, _query, *_args):
        return {
            "revision": 4,
            "current_planner_output": {
                "days": [{
                    "day": 1,
                    "stops": [{
                        "itemId": "planner:1:lake",
                        "placeId": "lake",
                        "notes": {
                            "text": "Source note",
                            "sourceType": "url",
                            "sourceUrl": "https://example.test/video",
                        },
                        "personalNotes": None,
                    }],
                }],
            },
        }

    async def execute(self, _query, *args):
        self.updated_args = args


def test_list_chats_projects_boolean_and_applies_page_bounds() -> None:
    connection = FakeConnection()
    repository = PostgresTripChatRepository("postgresql://unused")

    async def get_pool():
        return FakePool(connection)

    repository._get_pool = get_pool  # type: ignore[method-assign]
    result = asyncio.run(repository.list_chats(9, limit=12, offset=4))

    assert result[0].has_itinerary is True
    assert "current_planner_output," not in connection.query
    assert "AS has_itinerary" in connection.query
    assert connection.args == (9, 12, 4)


def test_personal_note_update_changes_only_planner_snapshot_personal_notes() -> None:
    connection = FakeMutationConnection()
    repository = PostgresTripChatRepository("postgresql://unused")

    async def get_pool():
        return FakePool(connection)

    repository._get_pool = get_pool  # type: ignore[method-assign]
    status = asyncio.run(
        repository.update_personal_notes(
            9,
            "chat-1",
            expected_revision=4,
            day=1,
            item_id="planner:1:lake",
            personal_notes="Nhớ mang ô",
        )
    )

    saved = json.loads(connection.updated_args[0])
    stop = saved["days"][0]["stops"][0]
    assert status == "updated"
    assert stop["personalNotes"] == "Nhớ mang ô"
    assert stop["notes"]["text"] == "Source note"
