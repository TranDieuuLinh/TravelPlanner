from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.auth.adapters.in_memory import InMemoryUserRepository
from app.modules.auth.service import AuthService
from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.service import ObservabilityService


def test_observability_requires_admin_and_reports_local_store() -> None:
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
    assert status.json()["configured"] is True
    assert status.json()["reachable"] is True


def test_observations_can_be_filtered_to_one_trace(tmp_path) -> None:
    app = create_app()
    app.state.auth_service = AuthService(
        InMemoryUserRepository(),
        bootstrap_users=[("admin@example.com", "Admin", "Password123!", "admin")],
    )
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    app.state.observability_service = ObservabilityService(store)
    store.start_trace("trace-1", {})
    store.start_observation("trace-1", "tool", "first")
    store.start_trace("trace-2", {})
    store.start_observation("trace-2", "tool", "second")

    with TestClient(app) as http:
        http.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "Password123!"},
        )
        response = http.get(
            "/admin/observability/observations?traceId=trace-2"
        )

    assert response.status_code == 200
    assert [item["traceId"] for item in response.json()["items"]] == ["trace-2"]
