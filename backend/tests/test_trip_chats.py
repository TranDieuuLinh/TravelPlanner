from app.modules.plans.chat_model import TripChat, TripChatMessage, TripRevision
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_schema import TripChatTurnRead
from app.modules.users.repository import UserRepository
from tests.helpers import csrf_headers


def test_trip_chat_requires_authentication(client) -> None:
    response = client.get("/api/trip-chats")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_user_can_create_and_list_own_trip_chats(registered_client) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Paris spring trip"},
        headers=csrf_headers(registered_client),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Paris spring trip"
    assert body["revision"] == 0
    assert body["currentPlan"] is None

    listed = registered_client.get("/api/trip-chats")
    assert listed.status_code == 200
    assert [(chat["id"], chat["title"]) for chat in listed.json()] == [
        (body["id"], "Paris spring trip")
    ]


def test_active_turn_is_restored_and_listed_for_background_loading(
    registered_client,
) -> None:
    chat = registered_client.post(
        "/api/trip-chats",
        json={"title": "Đà Nẵng chạy nền"},
        headers=csrf_headers(registered_client),
    ).json()
    created_turn = registered_client.post(
        f"/api/trip-chats/{chat['id']}/turns",
        json={
            "content": "Lập kế hoạch Đà Nẵng 3 ngày",
            "expectedRevision": 0,
            "clientTurnId": "background-loading-turn",
            "attachmentNames": [],
        },
        headers=csrf_headers(registered_client),
    )

    assert created_turn.status_code == 201
    assert created_turn.json()["status"] == "queued"

    active = registered_client.get("/api/trip-chats/active-turns")
    assert active.status_code == 200
    assert [(turn["chatId"], turn["status"]) for turn in active.json()] == [
        (chat["id"], "queued")
    ]

    restored_chat = registered_client.get(f"/api/trip-chats/{chat['id']}")
    assert restored_chat.status_code == 200
    assert restored_chat.json()["turns"][0]["id"] == created_turn.json()["id"]


def test_user_cannot_read_another_users_trip_chat(registered_client) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    registered_client.post(
        "/api/auth/logout",
        headers=csrf_headers(registered_client),
    )
    second_user = registered_client.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "password": "MatKhauManh123",
            "fullName": "Second User",
        },
    )
    assert second_user.status_code == 201

    response = registered_client.get(f"/api/trip-chats/{chat_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "TRIP_CHAT_NOT_FOUND"


def test_user_can_delete_own_trip_chat_and_its_history(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Lịch sử cần xóa"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    db_session.add_all(
        [
            TripChatMessage(
                id="message-to-delete",
                chat_id=chat_id,
                role="user",
                content="Tạo chuyến đi Hà Nội",
                sequence=1,
                attachment_names=[],
                plan_revision=1,
            ),
            TripRevision(
                id="revision-to-delete",
                chat_id=chat_id,
                revision=1,
                intake_id=None,
                plan_payload={},
                trip_intent_payload=None,
            ),
        ]
    )
    db_session.commit()

    response = registered_client.delete(
        f"/api/trip-chats/{chat_id}",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 204
    assert registered_client.get(f"/api/trip-chats/{chat_id}").status_code == 404
    assert db_session.get(TripChatMessage, "message-to-delete") is None
    assert db_session.get(TripRevision, "revision-to-delete") is None


def test_delete_trip_chat_requires_csrf(registered_client) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={},
        headers=csrf_headers(registered_client),
    )

    response = registered_client.delete(f"/api/trip-chats/{created.json()['id']}")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


def test_user_can_delete_all_own_trip_chats_without_deleting_another_users_chats(
    registered_client,
    db_session,
) -> None:
    own_chat_ids = [
        registered_client.post(
            "/api/trip-chats",
            json={"title": title},
            headers=csrf_headers(registered_client),
        ).json()["id"]
        for title in ("Hà Nội", "Đà Nẵng")
    ]
    registered_client.post(
        "/api/auth/logout",
        headers=csrf_headers(registered_client),
    )
    registered_client.post(
        "/api/auth/register",
        json={
            "email": "bulk-delete-second@example.com",
            "password": "MatKhauManh123",
            "fullName": "Second User",
        },
    )
    other_chat_id = registered_client.post(
        "/api/trip-chats",
        json={"title": "Chat cần giữ"},
        headers=csrf_headers(registered_client),
    ).json()["id"]
    registered_client.post(
        "/api/auth/logout",
        headers=csrf_headers(registered_client),
    )
    registered_client.post(
        "/api/auth/login",
        json={
            "email": "traveler@example.com",
            "password": "MatKhauManh123",
        },
    )

    response = registered_client.delete(
        "/api/trip-chats",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 204
    assert registered_client.get("/api/trip-chats").json() == []
    assert all(db_session.get(TripChat, chat_id) is None for chat_id in own_chat_ids)
    assert db_session.get(TripChat, other_chat_id) is not None


def test_delete_all_trip_chats_requires_csrf(registered_client) -> None:
    response = registered_client.delete("/api/trip-chats")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


def test_turn_lifecycle_reuses_user_message_row(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Hà Nội")

    turn = repository.create_turn(
        chat,
        client_turn_id="client-turn-1",
        content="Tạo chuyến Hà Nội",
        attachment_names=[],
        expected_revision=0,
    )
    repository.save_conversation_response(
        repository.get(chat.id, user.id),
        turn,
        assistant_content="Đã hiểu.",
        assistant_blocks=[{"type": "text", "text": "Đã hiểu."}],
    )
    repository.update_turn(turn, status="completed")

    stored = repository.get(chat.id, user.id)
    assert [message.role for message in stored.messages] == ["user", "assistant"]
    assert stored.messages[0].client_turn_id == "client-turn-1"
    assert stored.messages[0].status == "completed"
    assert stored.messages[1].turn_id == turn.id
    assert TripChatTurnRead.model_validate(stored.messages[0]).id == turn.id


def test_user_cannot_delete_another_users_trip_chat(registered_client) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    registered_client.post(
        "/api/auth/logout",
        headers=csrf_headers(registered_client),
    )
    registered_client.post(
        "/api/auth/register",
        json={
            "email": "delete-second@example.com",
            "password": "MatKhauManh123",
            "fullName": "Second User",
        },
    )

    response = registered_client.delete(
        f"/api/trip-chats/{chat_id}",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "TRIP_CHAT_NOT_FOUND"


def test_user_can_reorder_trip_chat_items_with_repeated_form_fields(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Hà Nội cuối tuần"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.destination = "Hà Nội"
    chat.revision = 1
    chat.current_plan = {
        "id": "reorder-plan",
        "kind": "main",
        "status": "draft",
        "title": "Hà Nội cuối tuần",
        "destination": "Hà Nội",
        "intent": {
            "destination": "Hà Nội",
            "days": 1,
            "budget": "medium",
            "travelStyle": "local",
            "pace": "balanced",
        },
        "macroPlan": {
            "title": "Hà Nội cuối tuần",
            "destination": "Hà Nội",
            "selectionDays": [
                {"day": 1, "theme": "Ẩm thực", "targetArea": "Hoàn Kiếm"}
            ],
        },
        "days": [
            {
                "day": 1,
                "theme": "Ẩm thực",
                "items": [
                    {
                        "itemId": "coffee-9",
                        "name": "Coffee 9",
                        "timeWindow": "09:00-10:00",
                        "placeType": "cafe",
                        "source": "url",
                    },
                    {
                        "itemId": "bo-kho-phuong-dung",
                        "name": "Bò khô Phương Dung",
                        "timeWindow": "10:15-11:15",
                        "placeType": "food",
                        "source": "selected_place",
                    },
                ],
            }
        ],
    }
    db_session.commit()

    response = registered_client.put(
        f"/api/trip-chats/{chat_id}/plan/days/1/items/reorder",
        data={
            "expectedRevision": "1",
            "itemIds": ["bo-kho-phuong-dung", "coffee-9"],
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert [item["itemId"] for item in body["currentPlan"]["days"][0]["items"]] == [
        "bo-kho-phuong-dung",
        "coffee-9",
    ]
    assert body["messages"] == []


def test_user_can_save_personal_note_from_flat_form_data(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Ghi chú Hà Nội"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.destination = "Hà Nội"
    chat.revision = 1
    chat.current_plan = {
        "id": "personal-note-plan",
        "kind": "main",
        "status": "draft",
        "title": "Ghi chú Hà Nội",
        "destination": "Hà Nội",
        "intent": {
            "destination": "Hà Nội",
            "days": 1,
            "budget": "medium",
            "travelStyle": "local",
            "pace": "balanced",
        },
        "macroPlan": {
            "title": "Ghi chú Hà Nội",
            "destination": "Hà Nội",
            "selectionDays": [
                {"day": 1, "theme": "Ẩm thực", "targetArea": "Hoàn Kiếm"}
            ],
        },
        "days": [
            {
                "day": 1,
                "theme": "Ẩm thực",
                "items": [
                    {
                        "itemId": "pho-thin-bo-ho",
                        "name": "Phở Thìn Bờ Hồ",
                        "timeWindow": "08:00-09:00",
                        "placeType": "food",
                        "source": "url",
                        "notes": "Địa điểm lấy từ nội dung tham khảo.",
                    }
                ],
            }
        ],
    }
    db_session.commit()

    response = registered_client.patch(
        f"/api/trip-chats/{chat_id}/plan/days/1/items/pho-thin-bo-ho",
        data={
            "expectedRevision": "1",
            "personalNotes": "Ngồi ngoài trời và gọi món đặc trưng.",
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    item = body["currentPlan"]["days"][0]["items"][0]
    assert item["personalNotes"] == "Ngồi ngoài trời và gọi món đặc trưng."
    assert item["notes"] == "Địa điểm lấy từ nội dung tham khảo."
    assert body["messages"] == []


def test_user_can_save_transport_option_selection_from_trip_chat(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Hà Nội route"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.destination = "Hà Nội"
    chat.revision = 1
    chat.current_plan = {
        "id": "route-selection-plan",
        "kind": "main",
        "status": "draft",
        "title": "Hà Nội route",
        "destination": "Hà Nội",
        "intent": {
            "destination": "Hà Nội",
            "days": 1,
            "budget": "medium",
            "travelStyle": "local",
            "pace": "balanced",
        },
        "macroPlan": {
            "title": "Hà Nội route",
            "destination": "Hà Nội",
            "selectionDays": [
                {"day": 1, "theme": "Ẩm thực", "targetArea": "Hoàn Kiếm"}
            ],
        },
        "days": [
            {
                "day": 1,
                "theme": "Ẩm thực",
                "items": [
                    {
                        "itemId": "lake",
                        "name": "Hồ Hoàn Kiếm",
                        "timeWindow": "09:00-10:00",
                        "placeType": "attraction",
                        "source": "finder",
                    },
                    {
                        "itemId": "market",
                        "name": "Chợ Đồng Xuân",
                        "timeWindow": "10:15-11:15",
                        "placeType": "attraction",
                        "source": "finder",
                    },
                ],
                "transportLegs": [
                    {
                        "fromItemId": "lake",
                        "toItemId": "market",
                        "fromPlace": "Hồ Hoàn Kiếm",
                        "toPlace": "Chợ Đồng Xuân",
                        "mode": "car",
                        "distanceMeters": 2200,
                        "estimatedDurationMinutes": 12,
                        "geometryCoordinates": [
                            [21.0285, 105.8542],
                            [21.0375, 105.85],
                        ],
                        "source": "valhalla_routing",
                        "verified": True,
                        "alternatives": [
                            {
                                "mode": "walk",
                                "distanceMeters": 1600,
                                "estimatedDurationMinutes": 24,
                                "geometryCoordinates": [
                                    [21.0285, 105.8542],
                                    [21.0375, 105.85],
                                ],
                                "source": "valhalla_routing",
                                "verified": True,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    db_session.commit()

    response = registered_client.put(
        f"/api/trip-chats/{chat_id}/plan/days/1/transport-legs/0/selection",
        data={"expectedRevision": "1", "mode": "walk"},
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert body["messages"] == []
    leg = body["currentPlan"]["days"][0]["transportLegs"][0]
    assert leg["mode"] == "walk"
    assert leg["estimatedDurationMinutes"] == 24
    assert [option["mode"] for option in leg["alternatives"]] == ["car"]


def test_user_can_save_transport_option_selection_when_modes_repeat(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Hà Nội route variants"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.destination = "Hà Nội"
    chat.revision = 1
    chat.current_plan = {
        "id": "route-variant-plan",
        "kind": "main",
        "status": "draft",
        "title": "Hà Nội route variants",
        "destination": "Hà Nội",
        "intent": {
            "destination": "Hà Nội",
            "days": 1,
            "budget": "medium",
            "travelStyle": "local",
            "pace": "balanced",
        },
        "macroPlan": {
            "title": "Hà Nội route variants",
            "destination": "Hà Nội",
            "selectionDays": [
                {"day": 1, "theme": "Ẩm thực", "targetArea": "Hoàn Kiếm"}
            ],
        },
        "days": [
            {
                "day": 1,
                "theme": "Ẩm thực",
                "items": [
                    {
                        "itemId": "lake",
                        "name": "Hồ Hoàn Kiếm",
                        "timeWindow": "09:00-10:00",
                        "placeType": "attraction",
                        "source": "finder",
                    },
                    {
                        "itemId": "market",
                        "name": "Chợ Đồng Xuân",
                        "timeWindow": "10:15-11:15",
                        "placeType": "attraction",
                        "source": "finder",
                    },
                ],
                "transportLegs": [
                    {
                        "fromItemId": "lake",
                        "toItemId": "market",
                        "fromPlace": "Hồ Hoàn Kiếm",
                        "toPlace": "Chợ Đồng Xuân",
                        "mode": "public_transit",
                        "distanceMeters": 2900,
                        "estimatedDurationMinutes": 32,
                        "geometryCoordinates": [
                            [21.0285, 105.8542],
                            [21.0375, 105.85],
                        ],
                        "source": "opentripplanner_transit",
                        "verified": True,
                        "details": {
                            "lines": ["14"],
                            "segments": [
                                {
                                    "mode": "BUS",
                                    "line": "14",
                                    "estimatedDurationMinutes": 20,
                                    "distanceMeters": 2200,
                                }
                            ],
                        },
                        "alternatives": [
                            {
                                "mode": "public_transit",
                                "distanceMeters": 2900,
                                "estimatedDurationMinutes": 32,
                                "geometryCoordinates": [
                                    [21.0285, 105.8542],
                                    [21.0320, 105.852],
                                    [21.0375, 105.85],
                                ],
                                "source": "opentripplanner_transit",
                                "verified": True,
                                "details": {
                                    "lines": ["31"],
                                    "segments": [
                                        {
                                            "mode": "BUS",
                                            "line": "31",
                                            "estimatedDurationMinutes": 18,
                                            "distanceMeters": 2100,
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    db_session.commit()

    response = registered_client.put(
        f"/api/trip-chats/{chat_id}/plan/days/1/transport-legs/0/selection",
        data={
            "expectedRevision": "1",
            "mode": "public_transit",
            "optionKey": "public_transit::opentripplanner_transit::32::2900::31::BUS:31:18:2100",
            "source": "opentripplanner_transit",
            "distanceMeters": "2900",
            "estimatedDurationMinutes": "32",
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 200
    leg = response.json()["currentPlan"]["days"][0]["transportLegs"][0]
    assert leg["estimatedDurationMinutes"] == 32
    assert leg["distanceMeters"] == 2900
    assert leg["details"]["lines"] == ["31"]
    assert len(leg["geometryCoordinates"]) == 3
    assert [option["details"]["lines"] for option in leg["alternatives"]] == [["14"]]


def test_user_can_remove_an_unscheduled_place_from_trip_chat(
    registered_client,
    db_session,
) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={"title": "Hà Nội cuối tuần"},
        headers=csrf_headers(registered_client),
    )
    chat_id = created.json()["id"]
    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.destination = "Hà Nội"
    chat.revision = 1
    chat.current_plan = {
        "id": "unscheduled-plan",
        "kind": "main",
        "status": "draft",
        "title": "Hà Nội cuối tuần",
        "destination": "Hà Nội",
        "intent": {
            "destination": "Hà Nội",
            "days": 1,
            "budget": "medium",
            "travelStyle": "local",
            "pace": "balanced",
        },
        "macroPlan": {
            "title": "Hà Nội cuối tuần",
            "destination": "Hà Nội",
            "selectionDays": [
                {"day": 1, "theme": "Ẩm thực", "targetArea": "Hoàn Kiếm"}
            ],
        },
        "days": [{"day": 1, "theme": "Ẩm thực", "items": []}],
        "unscheduledPlaces": [
            {
                "placeId": "train-street-south",
                "name": "Hanoi Train Street (South)",
                "reasonCode": "no_day_capacity",
                "reason": "The fixed trip duration has no remaining slot.",
            }
        ],
    }
    db_session.commit()

    response = registered_client.request(
        "DELETE",
        f"/api/trip-chats/{chat_id}/plan/unscheduled-places",
        data={
            "expectedRevision": "1",
            "placeId": "train-street-south",
            "name": "Hanoi Train Street (South)",
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert body["currentPlan"]["unscheduledPlaces"] == []
    assert body["messages"] == []
