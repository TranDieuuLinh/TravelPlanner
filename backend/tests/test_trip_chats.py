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
