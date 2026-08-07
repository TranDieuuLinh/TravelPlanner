from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.security import hash_password
from app.modules.users.model import User
from tests.helpers import csrf_headers


def test_register_sets_session_and_returns_current_user(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "Traveler@Example.com",
            "password": "MatKhauManh123",
            "fullName": "Nguyễn Minh Tuấn",
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "traveler@example.com"
    assert response.json()["user"]["role"] == "traveler"
    assert client.cookies.get("travelplanner_access")
    assert client.cookies.get("travelplanner_refresh")
    assert client.cookies.get("travelplanner_csrf")

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["fullName"] == "Nguyễn Minh Tuấn"


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    payload = {
        "email": "traveler@example.com",
        "password": "MatKhauManh123",
        "fullName": "Nguyễn Minh Tuấn",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201

    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_rejects_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "traveler@example.com",
            "password": "matkhauthuong",
            "fullName": "Nguyễn Minh Tuấn",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["fieldErrors"]["password"] == (
        "Mật khẩu phải có ít nhất một chữ hoa."
    )


def test_login_uses_one_error_for_unknown_email_and_wrong_password(client: TestClient) -> None:
    unknown = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "WrongPassword1"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["code"] == "INVALID_CREDENTIALS"

    client.post(
        "/api/auth/register",
        json={
            "email": "traveler@example.com",
            "password": "MatKhauManh123",
            "fullName": "Nguyễn Minh Tuấn",
        },
    )
    client.cookies.clear()
    wrong = client.post(
        "/api/auth/login",
        json={"email": "traveler@example.com", "password": "WrongPassword1"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"


def test_refresh_rotates_token_and_rejects_reuse(registered_client: TestClient) -> None:
    old_refresh = registered_client.cookies.get("travelplanner_refresh")
    old_csrf = registered_client.cookies.get("travelplanner_csrf")
    assert old_refresh and old_csrf

    refreshed = registered_client.post(
        "/api/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
    )
    assert refreshed.status_code == 200
    assert registered_client.cookies.get("travelplanner_refresh") != old_refresh

    registered_client.cookies.set("travelplanner_refresh", old_refresh)
    registered_client.cookies.set("travelplanner_csrf", old_csrf)
    reused = registered_client.post(
        "/api/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
    )
    assert reused.status_code == 401
    assert reused.json()["code"] == "SESSION_REUSED"


def test_logout_revokes_session_and_clears_cookies(registered_client: TestClient) -> None:
    response = registered_client.post(
        "/api/auth/logout",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 204
    assert registered_client.cookies.get("travelplanner_access") is None
    assert registered_client.get("/api/me").status_code == 401


def test_admin_users_endpoint_rejects_traveler(registered_client: TestClient) -> None:
    response = registered_client.get("/api/users")
    assert response.status_code == 403
    assert response.json()["code"] == "INSUFFICIENT_ROLE"


def test_admin_can_list_users(client: TestClient, db_session: Session) -> None:
    db_session.add(
        User(
            email="admin@example.com",
            full_name="Quản trị viên",
            role="admin",
            status="active",
            password_hash=hash_password("MatKhauAdmin123"),
        )
    )
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "MatKhauAdmin123"},
    )
    assert login.status_code == 200

    response = client.get("/api/users")
    assert response.status_code == 200
    assert response.json()[0]["role"] == "admin"


def test_banned_user_cannot_use_authenticated_endpoint(
    registered_client: TestClient,
    db_session: Session,
) -> None:
    user = db_session.scalar(select(User).where(User.email == "traveler@example.com"))
    assert user
    user.status = "banned"
    db_session.commit()

    response = registered_client.get("/api/me")
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_NOT_ACTIVE"
