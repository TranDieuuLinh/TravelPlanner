from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.planning_runs.model import PlanningRun, PlanningRunStage
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.service import PlanService


def test_explorer_failure_recording_recovers_failed_transaction() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[PlanningRun.__table__, PlanningRunStage.__table__],
    )

    with Session(engine) as session:
        repository = PlanningRunRepository(session)
        run_id = repository.start(
            source="explorer_intake",
            destination="Hà Nội",
        )
        session.add(
            PlanningRun(
                id=run_id,
                source="explorer_intake",
                mode="main",
                destination="Hà Nội",
                status="running",
                stage_count=0,
                summary_json={},
            )
        )
        try:
            session.flush()
        except IntegrityError:
            pass

        service = object.__new__(PlanService)
        service.planning_runs = repository
        service._fail_explorer_run(
            run_id,
            {"rawRequest": "https://example.com/video"},
            RuntimeError("Explorer persistence failed"),
        )

        run, stages = repository.get(run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error_code == "RuntimeError"
        assert len(stages) == 1
        assert stages[0].status == "failed"

    engine.dispose()
