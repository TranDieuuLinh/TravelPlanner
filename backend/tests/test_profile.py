from fastapi.testclient import TestClient

from tests.helpers import csrf_headers


def test_profile_update_requires_csrf(registered_client: TestClient) -> None:
    response = registered_client.patch(
        "/api/me/profile",
        json={"bio": "Tôi thích những hành trình có nhịp độ vừa phải."},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


def test_update_profile_persists_normalized_data(registered_client: TestClient) -> None:
    response = registered_client.patch(
        "/api/me/profile",
        headers=csrf_headers(registered_client),
        json={
            "fullName": "Nguyễn Tuấn",
            "bio": "Tôi thích những hành trình có nhịp độ vừa phải.",
            "travelPreferences": ["ẩm thực", " biển ", "ẩm thực"],
        },
    )

    assert response.status_code == 200
    assert response.json()["fullName"] == "Nguyễn Tuấn"
    assert response.json()["travelPreferences"] == ["ẩm thực", "biển"]
    assert registered_client.get("/api/me").json()["bio"].startswith("Tôi thích")


def test_submit_creator_application(registered_client: TestClient) -> None:
    response = registered_client.post(
        "/api/me/creator-application",
        headers=csrf_headers(registered_client),
        json={
            "bio": "Tôi xây dựng lịch trình ẩm thực và văn hóa tại miền Trung.",
            "portfolioUrls": ["https://example.com/portfolio"],
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "traveler"
    assert response.json()["creatorStatus"] == "pending"
    assert response.json()["creatorPortfolioUrls"] == ["https://example.com/portfolio"]

    duplicate = registered_client.post(
        "/api/me/creator-application",
        headers=csrf_headers(registered_client),
        json={
            "bio": "Tôi xây dựng lịch trình ẩm thực và văn hóa tại miền Trung.",
            "portfolioUrls": [],
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CREATOR_APPLICATION_PENDING"
