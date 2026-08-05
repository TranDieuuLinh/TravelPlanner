from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.modules.preferences.model import TravelerPreferenceSignal
from app.modules.users.model import User
from tests.helpers import csrf_headers


def test_profile_update_requires_csrf(registered_client: TestClient) -> None:
    response = registered_client.patch(
        "/api/me/profile",
        json={"bio": "Tôi thích những hành trình có nhịp độ vừa phải."},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


def test_update_profile_persists_normalized_data(
    registered_client: TestClient,
    db_session,
) -> None:
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

    assert "travel_preferences" not in {
        column.key for column in inspect(User).columns
    }
    signals = list(db_session.scalars(select(TravelerPreferenceSignal)))
    assert [signal.label for signal in signals] == ["ẩm thực", "biển"]
    assert all(signal.origin == "explicit" for signal in signals)


def test_traveler_profile_can_be_reviewed_updated_and_deleted(
    registered_client: TestClient,
) -> None:
    empty = registered_client.get("/api/me/traveler-profile")

    assert empty.status_code == 200
    assert empty.json()["signals"] == []

    updated = registered_client.patch(
        "/api/me/traveler-profile",
        headers=csrf_headers(registered_client),
        json={"explicitPreferences": ["ẩm thực địa phương", "đi chậm"]},
    )

    assert updated.status_code == 200
    assert updated.json()["explicitPreferences"] == [
        "ẩm thực địa phương",
        "đi chậm",
    ]
    assert updated.json()["topPreferences"] == [
        "ẩm thực địa phương",
        "đi chậm",
    ]
    assert {signal["origin"] for signal in updated.json()["signals"]} == {
        "explicit"
    }

    denied = registered_client.delete("/api/me/traveler-profile")
    assert denied.status_code == 403

    deleted = registered_client.delete(
        "/api/me/traveler-profile",
        headers=csrf_headers(registered_client),
    )
    assert deleted.status_code == 204
    assert registered_client.get("/api/me/traveler-profile").json()["signals"] == []


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
