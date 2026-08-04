from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.planning_runs.model import PlanningRun, PlanningRunStage
from app.modules.planning_runs.redaction import safe_snapshot


class PlanningRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def rollback(self) -> None:
        self.session.rollback()

    def start(
        self,
        *,
        source: str,
        destination: str,
        mode: str = "main",
        user_id: int | None = None,
        intake_id: str | None = None,
        summary: dict | None = None,
    ) -> str:
        run_id = str(uuid4())
        self.session.add(
            PlanningRun(
                id=run_id,
                user_id=user_id,
                intake_id=intake_id,
                source=source,
                mode=mode,
                destination=destination or "unspecified",
                status="running",
                summary_json=safe_snapshot(summary or {}),
            )
        )
        self.session.commit()
        return run_id

    def add_stage(
        self,
        run_id: str,
        *,
        stage: str,
        status: str,
        input_data: object = None,
        output_data: object = None,
        duration_ms: int | None = None,
        error: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        run = self.session.get(PlanningRun, run_id)
        if run is None:
            return
        sequence = run.stage_count + 1
        self.session.add(
            PlanningRunStage(
                id=str(uuid4()),
                run_id=run_id,
                sequence=sequence,
                stage=stage,
                status=status,
                duration_ms=duration_ms,
                input_json=safe_snapshot(input_data or {}),
                output_json=safe_snapshot(output_data or {}),
                error_json=safe_snapshot(error or {}),
                metadata_json=safe_snapshot(metadata or {}),
            )
        )
        run.stage_count = sequence
        run.current_stage = stage
        self.session.commit()

    def complete(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run = self.session.get(PlanningRun, run_id)
        if run is None:
            return
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.summary_json = safe_snapshot(summary or run.summary_json)
        run.error_code = error_code
        run.error_message = (
            str(error_message)[:2_000] if error_message is not None else None
        )
        self.session.commit()

    def list(
        self,
        *,
        status: str | None = None,
        stage: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PlanningRun], int]:
        statement = select(PlanningRun)
        count_statement = select(func.count()).select_from(PlanningRun)
        if status:
            statement = statement.where(PlanningRun.status == status)
            count_statement = count_statement.where(PlanningRun.status == status)
        if stage:
            statement = statement.where(PlanningRun.current_stage == stage)
            count_statement = count_statement.where(
                PlanningRun.current_stage == stage
            )
        if query:
            pattern = f"%{query.strip()}%"
            criteria = or_(
                PlanningRun.destination.ilike(pattern),
                PlanningRun.id.ilike(pattern),
                PlanningRun.intake_id.ilike(pattern),
            )
            statement = statement.where(criteria)
            count_statement = count_statement.where(criteria)
        rows = list(
            self.session.scalars(
                statement
                .order_by(PlanningRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
        total = int(self.session.scalar(count_statement) or 0)
        return rows, total

    def get(self, run_id: str) -> tuple[PlanningRun | None, list[PlanningRunStage]]:
        run = self.session.get(PlanningRun, run_id)
        if run is None:
            return None, []
        stages = list(
            self.session.scalars(
                select(PlanningRunStage)
                .where(PlanningRunStage.run_id == run_id)
                .order_by(PlanningRunStage.sequence)
            ).all()
        )
        return run, stages
