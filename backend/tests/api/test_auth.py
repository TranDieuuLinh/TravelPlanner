from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.auth.adapters.in_memory import InMemoryUserRepository
from app.modules.auth.service import AuthService


def client(*, with_demo_admin: bool = False) -> TestClient:
    # Keep auth API tests isolated from a developer's cloud DATABASE_URL.
    app = create_app(Settings(app_env="test", database_url=None))
    app.state.auth_service = AuthService(
        InMemoryUserRepository(),
        bootstrap_users=(
            [("admin@travelplanner.local", "TravelPlanner Admin", "Password123!", "admin")]
            if with_demo_admin
            else []
        ),
    )
    return TestClient(app)


def test_register_login_bearer_refresh_and_logout_flow() -> None:
    with client() as http:
        registered = http.post(
            "/auth/register",
            json={
                "fullName": "Nguyen Traveller",
                "email": "new@example.com",
                "password": "StrongPass123",
            },
        )
        assert registered.status_code == 200
        assert registered.json()["user"]["email"] == "new@example.com"
        access_token = registered.json()["accessToken"]
        assert registered.json()["refreshToken"]
        refresh_token = registered.json()["refreshToken"]

        current = http.get("/me", headers={"Authorization": f"Bearer {access_token}"})
        assert current.status_code == 200
        assert current.json()["fullName"] == "Nguyen Traveller"

        refreshed = http.post("/auth/refresh", json={"refreshToken": refresh_token})
        assert refreshed.status_code == 200
        assert refreshed.json()["accessToken"] != access_token
        access_token = refreshed.json()["accessToken"]
        logged_out = http.post("/auth/logout", json={"refreshToken": refreshed.json()["refreshToken"]})
        assert logged_out.status_code == 204
        # Access JWTs are short-lived and stateless; logout revokes refresh
        # rotation and the frontend immediately discards this access token.
        assert http.get("/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 200


def test_login_rejects_invalid_credentials_and_register_validates_password() -> None:
    with client() as http:
        invalid_login = http.post(
            "/auth/login",
            json={"email": "unknown@example.com", "password": "WrongPass123"},
        )
        assert invalid_login.status_code == 401
        assert invalid_login.json()["detail"]["code"] == "INVALID_CREDENTIALS"

        invalid_register = http.post(
            "/auth/register",
            json={"fullName": "A", "email": "bad", "password": "short"},
        )
        assert invalid_register.status_code == 400
        assert invalid_register.json()["detail"]["fieldErrors"]["password"]


def test_demo_admin_can_login_and_refresh_requires_a_token() -> None:
    with client(with_demo_admin=True) as http:
        logged_in = http.post(
            "/auth/login",
            json={"email": "admin@travelplanner.local", "password": "Password123!"},
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["user"]["role"] == "admin"
        assert http.post("/auth/refresh").status_code == 401
