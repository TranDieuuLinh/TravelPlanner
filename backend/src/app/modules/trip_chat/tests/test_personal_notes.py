import asyncio

from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository


def test_personal_notes_update_preserves_read_only_source_note() -> None:
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))
    planner_output = {
        "destination": "Hà Nội",
        "days": [
            {
                "day": 1,
                "stops": [
                    {
                        "itemId": "planner:1:lake",
                        "placeId": "lake",
                        "notes": {
                            "text": "Đến trước 8 giờ",
                            "sourceType": "url",
                            "sourceUrl": "https://example.test/video",
                        },
                        "personalNotes": None,
                    }
                ],
            }
        ],
    }
    chat = asyncio.run(
        repository.append_exchange(
            7,
            chat.id,
            "Tạo lịch",
            {"content": "Đã tạo"},
            None,
            planner_output,
        )
    )
    assert chat is not None

    status = asyncio.run(
        repository.update_personal_notes(
            7,
            chat.id,
            expected_revision=chat.revision,
            day=1,
            item_id="planner:1:lake",
            personal_notes="  Nhớ mang ô  ",
        )
    )
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    assert updated is not None
    stop = updated.current_planner_output["days"][0]["stops"][0]
    assert stop["personalNotes"] == "  Nhớ mang ô  "
    assert stop["notes"] == planner_output["days"][0]["stops"][0]["notes"]


def test_personal_notes_update_rejects_stale_revision() -> None:
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))

    status = asyncio.run(
        repository.update_personal_notes(
            7,
            chat.id,
            expected_revision=chat.revision - 1,
            day=1,
            item_id="missing",
            personal_notes="Không được lưu",
        )
    )

    assert status == "revision_conflict"
