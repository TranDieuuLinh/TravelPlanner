import asyncio

from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository


def _chat_with_leg():
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))
    output = {
        "destination": "Hà Nội",
        "days": [{
            "day": 1,
            "legs": [{
                "fromPlaceId": "lake",
                "toPlaceId": "museum",
                "durationMinutes": 12,
                "distanceMeters": 1800,
                "provider": "valhalla",
            }],
        }],
    }
    chat = asyncio.run(repository.append_exchange(
        7, chat.id, "Tạo lịch", {"content": "Đã tạo"}, None, output
    ))
    assert chat is not None
    return repository, chat


def test_select_transport_option_persists_choice_and_increments_revision() -> None:
    repository, chat = _chat_with_leg()
    selection = {
        "mode": "walk",
        "source": "valhalla",
        "distanceMeters": 1800,
        "estimatedDurationMinutes": 24,
        "geometryCoordinates": [[21.0, 105.8], [21.01, 105.81]],
        "verified": True,
    }

    status = asyncio.run(repository.select_transport_option(
        7,
        chat.id,
        expected_revision=chat.revision,
        day=1,
        leg_index=0,
        selection=selection,
    ))
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    assert updated is not None
    assert updated.revision == chat.revision + 1
    assert updated.current_planner_output["days"][0]["legs"][0][
        "selectedTransport"
    ] == selection


def test_select_transport_option_rejects_unknown_leg_without_writing() -> None:
    repository, chat = _chat_with_leg()

    status = asyncio.run(repository.select_transport_option(
        7,
        chat.id,
        expected_revision=chat.revision,
        day=1,
        leg_index=2,
        selection={"mode": "car"},
    ))
    unchanged = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "leg_not_found"
    assert unchanged is not None
    assert unchanged.revision == chat.revision
