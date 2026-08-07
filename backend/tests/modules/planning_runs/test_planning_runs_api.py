from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.modules.auth.security import hash_password
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.users.model import User


def _admin_client(client: TestClient, db_session: Session) -> TestClient:
    db_session.add(
        User(
            email="planning-admin@example.com",
            full_name="Planning Admin",
            role="admin",
            status="active",
            password_hash=hash_password("PlanningAdmin123"),
        )
    )
    db_session.commit()
    response = client.post(
        "/api/auth/login",
        json={
            "email": "planning-admin@example.com",
            "password": "PlanningAdmin123",
        },
    )
    assert response.status_code == 200
    return client


def test_admin_can_list_and_read_redacted_planning_run(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = PlanningRunRepository(db_session)
    run_id = repository.start(
        source="explorer",
        destination="Hà Nội",
        summary={"days": 3},
    )
    repository.add_stage(
        run_id,
        stage="explorer",
        status="completed",
        input_data={
            "rawRequest": "Lập lịch trình riêng tư",
            "urls": ["https://example.com/video?token=secret"],
            "imageContexts": [{"bytes": "never-store-this"}],
        },
        output_data={"candidateCount": 4},
        duration_ms=125,
    )
    repository.complete(
        run_id,
        status="completed",
        summary={"candidateCount": 4},
    )

    admin = _admin_client(client, db_session)
    list_response = admin.get("/api/admin/planning-runs")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["destination"] == "Hà Nội"

    detail_response = admin.get(f"/api/admin/planning-runs/{run_id}")
    assert detail_response.status_code == 200
    stage_input = detail_response.json()["stages"][0]["input"]
    assert stage_input["rawRequest"] == {
        "characterCount": 23,
        "present": True,
    }
    assert stage_input["urls"] == ["https://example.com/video"]
    assert stage_input["imageContexts"] == {"count": 1}
    assert "never-store-this" not in detail_response.text


def test_non_admin_cannot_read_planning_runs(
    registered_client: TestClient,
    db_session: Session,
) -> None:
    PlanningRunRepository(db_session).start(
        source="direct",
        destination="Đà Nẵng",
    )

    response = registered_client.get("/api/admin/planning-runs")

    assert response.status_code == 403


def test_admin_can_inspect_golden_dataset_contract_issues(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _admin_client(client, db_session)

    response = admin.get(
        "/api/admin/planning-runs/golden/cases",
        params={"module": "checker_backup"},
    )

    assert response.status_code == 200
    cases = {item["id"]: item for item in response.json()["items"]}
    assert cases["CHK-001"]["validation"]["status"] == "invalid"
    assert any(
        issue["path"] == "goldenOutput.checkReport.issues[0].violationCode"
        for issue in cases["CHK-001"]["validation"]["issues"]
    )


def test_admin_can_execute_checker_golden_case(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _admin_client(client, db_session)

    response = admin.post(
        "/api/admin/planning-runs/golden/cases/CHK-001/run",
        headers={"X-CSRF-Token": admin.cookies.get("travelplanner_csrf")},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["module"] == "checker_backup"
    assert result["actualOutput"]["checkReport"]["summary"]
    assert result["comparison"]["mismatchCount"] > 0

    run, stages = PlanningRunRepository(db_session).get(result["runId"])
    assert run is not None
    assert run.source == "golden_dataset"
    assert run.status == "completed"
    assert stages[0].stage == "checker_backup"


def test_invalid_golden_input_returns_inspectable_execution_failure(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _admin_client(client, db_session)

    response = admin.post(
        "/api/admin/planning-runs/golden/cases/FND-002/run",
        headers={"X-CSRF-Token": admin.cookies.get("travelplanner_csrf")},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["error"]["code"] == "GOLDEN_INPUT_INVALID"
    assert result["error"]["details"]
