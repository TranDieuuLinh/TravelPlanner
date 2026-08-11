from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.auth.adapters.in_memory import InMemoryUserRepository
from app.modules.auth.service import AuthService


def test_observability_requires_admin_and_reports_missing_configuration() -> None:
    app = create_app()
    app.state.auth_service = AuthService(
        InMemoryUserRepository(),
        bootstrap_users=[("admin@example.com", "Admin", "Password123!", "admin")],
    )

    with TestClient(app) as http:
        assert http.get("/admin/observability/status").status_code == 401
        login = http.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "Password123!"},
        )
        assert login.status_code == 200
        status = http.get("/admin/observability/status")

    assert status.status_code == 200
    assert status.json()["configured"] is False
