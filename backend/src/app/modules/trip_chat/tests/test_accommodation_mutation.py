import asyncio

from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository


def _chat_with_accommodation():
    repository = InMemoryTripChatRepository()
    chat = asyncio.run(repository.create_chat(7, "Hà Nội"))
    output = {
        "accommodation": {
            "placeId": "hotel-old",
            "name": "Old Hotel",
            "coordinates": {"latitude": 21.0, "longitude": 105.8},
            "pricePerNight": {"cost": 300000, "currency": "VND"},
        },
        "accommodationNights": 1,
        "totalCostPerPerson": 450000,
        "days": [{
            "day": 1,
            "legs": [{"fromPlaceId": "hotel-old", "toPlaceId": "lake"}],
            "costPerPerson": 450000,
            "costBreakdown": {"accommodation": 300000, "total": 450000},
        }],
    }
    chat = asyncio.run(repository.append_exchange(
        7, chat.id, "Tạo lịch", {"content": "Đã tạo"}, None, output
    ))
    assert chat is not None
    return repository, chat


def test_update_accommodation_updates_linked_route_and_note() -> None:
    repository, chat = _chat_with_accommodation()
    status = asyncio.run(repository.update_accommodation(
        7,
        chat.id,
        expected_revision=chat.revision,
        changes={
            "placeId": "hotel-new",
            "name": "New Hotel",
            "latitude": 21.1,
            "longitude": 105.9,
            "personalNotes": "Nhận phòng sau 14h",
        },
    ))
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    accommodation = updated.current_planner_output["accommodation"]
    assert accommodation["name"] == "New Hotel"
    assert accommodation["coordinates"] == {"latitude": 21.1, "longitude": 105.9}
    assert accommodation["personalNotes"] == "Nhận phòng sau 14h"
    assert updated.current_planner_output["days"][0]["legs"][0]["fromPlaceId"] == "hotel-new"


def test_delete_accommodation_removes_routes_and_cost() -> None:
    repository, chat = _chat_with_accommodation()
    status = asyncio.run(repository.update_accommodation(
        7, chat.id, expected_revision=chat.revision, changes=None, delete=True
    ))
    updated = asyncio.run(repository.get_chat(7, chat.id))

    assert status == "updated"
    assert updated.current_planner_output["accommodation"] is None
    assert updated.current_planner_output["days"][0]["legs"] == []
    assert updated.current_planner_output["days"][0]["costBreakdown"]["accommodation"] == 0
    assert updated.current_planner_output["days"][0]["costPerPerson"] == 150000
    assert updated.current_planner_output["totalCostPerPerson"] == 150000
