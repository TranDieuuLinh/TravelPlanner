import asyncio

from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository


def _chat_with_unscheduled_place():
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))
    output = {
        "destination": "Hà Nội",
        "days": [{"day": 1, "stops": [], "legs": []}],
        "unscheduled": [{
            "placeId": "unresolved:train-street",
            "name": "Hanoi Train Street",
            "reasonCode": "identity_needs_review",
            "message": "Cần xác nhận địa điểm.",
            "sourceRefs": ["https://www.youtube.com/watch?v=train-street"],
        }],
    }
    chat = asyncio.run(repository.append_exchange(
        7, chat.id, "Lên lịch", {"content": "Đã tạo"}, None, output
    ))
    assert chat is not None
    return repository, chat


def test_confirm_unscheduled_place_moves_selected_match_into_day() -> None:
    repository, chat = _chat_with_unscheduled_place()

    status = asyncio.run(repository.confirm_unscheduled_place(
        7,
        chat.id,
        expected_revision=chat.revision,
        name="Hanoi Train Street",
        place_id="unresolved:train-street",
        candidate_id=None,
        day=1,
        item={
            "placeId": "kg:train-street",
            "name": "Hanoi Train Street",
            "latitude": 21.035,
            "longitude": 105.845,
            "placeType": "attraction",
            "sourceRefs": ["https://www.youtube.com/watch?v=train-street"],
            "sourceProvider": "youtube",
        },
    ))

    updated = asyncio.run(repository.get_chat(7, chat.id))
    assert status == "updated"
    assert updated is not None
    assert updated.revision == chat.revision + 1
    assert updated.current_planner_output["days"][0]["stops"][0]["placeId"] == "kg:train-street"
    assert updated.current_planner_output["days"][0]["stops"][0]["sourceRefs"] == [
        "https://www.youtube.com/watch?v=train-street"
    ]
    assert updated.current_planner_output["days"][0]["stops"][0]["sourceProvider"] == "youtube"
    assert updated.current_planner_output["unscheduled"] == []


def test_remove_unscheduled_place_is_revision_checked() -> None:
    repository, chat = _chat_with_unscheduled_place()

    assert asyncio.run(repository.remove_unscheduled_place(
        7,
        chat.id,
        expected_revision=chat.revision - 1,
        name="Hanoi Train Street",
        place_id="unresolved:train-street",
        candidate_id=None,
    )) == "revision_conflict"

    status = asyncio.run(repository.remove_unscheduled_place(
        7,
        chat.id,
        expected_revision=chat.revision,
        name="Hanoi Train Street",
        place_id="unresolved:train-street",
        candidate_id=None,
    ))
    assert status == "updated"
