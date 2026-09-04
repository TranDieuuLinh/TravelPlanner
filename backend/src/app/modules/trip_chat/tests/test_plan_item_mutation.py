import asyncio

from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository


def _chat_with_plan_items():
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))
    output = {
        "destination": "Hà Nội",
        "days": [{
            "day": 1,
            "stops": [
                {
                    "itemId": "planner:1:a",
                    "placeId": "a",
                    "name": "A",
                    "position": 0,
                    "coordinates": {"latitude": 21.01, "longitude": 105.81},
                },
                {
                    "itemId": "planner:1:b",
                    "placeId": "b",
                    "name": "B",
                    "position": 1,
                    "coordinates": {"latitude": 21.02, "longitude": 105.82},
                },
                {
                    "itemId": "planner:1:c",
                    "placeId": "c",
                    "name": "C",
                    "position": 2,
                    "coordinates": {"latitude": 21.03, "longitude": 105.83},
                },
            ],
            "legs": [
                {"fromPlaceId": "a", "toPlaceId": "b"},
                {"fromPlaceId": "b", "toPlaceId": "c"},
            ],
        }],
    }
    chat = asyncio.run(repository.append_exchange(
        7, chat.id, "Tạo lịch", {"content": "Đã tạo"}, None, output
    ))
    assert chat is not None
    return repository, chat


def test_delete_plan_item_removes_only_item_and_touching_legs() -> None:
    repository, chat = _chat_with_plan_items()

    status = asyncio.run(repository.delete_plan_item(
        7,
        chat.id,
        expected_revision=chat.revision,
        day=1,
        item_id="planner:1:b",
    ))
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    assert updated is not None
    assert updated.revision == chat.revision + 1
    day = updated.current_planner_output["days"][0]
    assert [stop["itemId"] for stop in day["stops"]] == [
        "planner:1:a",
        "planner:1:c",
    ]
    assert [stop["position"] for stop in day["stops"]] == [0, 1]
    assert day["legs"] == []


def test_update_plan_item_changes_location_and_invalidates_touching_legs() -> None:
    repository, chat = _chat_with_plan_items()

    status = asyncio.run(repository.update_plan_item(
        7,
        chat.id,
        expected_revision=chat.revision,
        day=1,
        item_id="planner:1:b",
        changes={
            "placeId": "b-new",
            "name": "B mới",
            "latitude": 21.22,
            "longitude": 105.92,
        },
    ))
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    assert updated is not None
    stop = updated.current_planner_output["days"][0]["stops"][1]
    assert stop["placeId"] == "b-new"
    assert stop["name"] == "B mới"
    assert stop["coordinates"] == {"latitude": 21.22, "longitude": 105.92}
    assert updated.current_planner_output["days"][0]["legs"] == []


def test_plan_item_mutations_reject_stale_revision_and_unknown_item() -> None:
    repository, chat = _chat_with_plan_items()

    assert asyncio.run(repository.delete_plan_item(
        7,
        chat.id,
        expected_revision=chat.revision - 1,
        day=1,
        item_id="planner:1:b",
    )) == "revision_conflict"
    assert asyncio.run(repository.delete_plan_item(
        7,
        chat.id,
        expected_revision=chat.revision,
        day=1,
        item_id="missing",
    )) == "item_not_found"


def test_replace_plan_output_is_atomic_on_revision() -> None:
    repository, chat = _chat_with_plan_items()
    replacement = {"destination": "Hà Nội", "days": [{"day": 1, "stops": []}]}

    assert asyncio.run(repository.replace_plan_output(
        7,
        chat.id,
        expected_revision=chat.revision - 1,
        output=replacement,
    )) == "revision_conflict"
    assert asyncio.run(repository.replace_plan_output(
        7,
        chat.id,
        expected_revision=chat.revision,
        output=replacement,
    )) == "updated"
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert updated is not None
    assert updated.revision == chat.revision + 1
    assert updated.current_planner_output == replacement
