from app.modules.plans.chat_model import TripChatMessage, TripChatPlanRevision
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
            TripChatPlanRevision(
                id="revision-to-delete",
                chat_id=chat_id,
                revision=1,
                intake_id=None,
                plan_payload={},
                explorer_payload={},
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
    assert db_session.get(TripChatPlanRevision, "revision-to-delete") is None


def test_delete_trip_chat_requires_csrf(registered_client) -> None:
    created = registered_client.post(
        "/api/trip-chats",
        json={},
        headers=csrf_headers(registered_client),
    )

    response = registered_client.delete(f"/api/trip-chats/{created.json()['id']}")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


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
