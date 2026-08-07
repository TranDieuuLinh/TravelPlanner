from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.plans.chat_model import TripChat, TripChatMessage
from app.modules.preferences.observation_model import PreferenceObservationJob


class PreferenceObservationJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        message_id: str,
        user_id: int,
        commit: bool = True,
    ) -> PreferenceObservationJob:
        existing = self.db.scalar(
            select(PreferenceObservationJob).where(
                PreferenceObservationJob.message_id == message_id
            )
        )
        if existing is not None:
            return existing
        job = PreferenceObservationJob(
            message_id=message_id,
            user_id=user_id,
            status="queued",
        )
        self.db.add(job)
        try:
            if commit:
                self.db.commit()
                self.db.refresh(job)
            else:
                self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(PreferenceObservationJob).where(
                    PreferenceObservationJob.message_id == message_id
                )
            )
            if existing is None:
                raise
            return existing
        return job

    def recover_interrupted(self) -> int:
        result = self.db.execute(
            update(PreferenceObservationJob)
            .where(PreferenceObservationJob.status == "running")
            .values(status="queued", started_at=None, updated_at=datetime.now(UTC))
        )
        self.db.commit()
        return result.rowcount or 0

    def claim_next(self) -> PreferenceObservationJob | None:
        statement = (
            select(PreferenceObservationJob)
            .join(
                TripChatMessage,
                TripChatMessage.id == PreferenceObservationJob.message_id,
            )
            .where(
                PreferenceObservationJob.status == "queued",
                TripChatMessage.status == "completed",
            )
            .order_by(PreferenceObservationJob.created_at, PreferenceObservationJob.id)
            .limit(1)
        )
        if self.db.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = self.db.scalar(statement)
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error_code = None
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def skip_ineligible_turns(self) -> int:
        terminal_message_ids = select(TripChatMessage.id).where(
            (TripChatMessage.status.in_({"failed", "cancelled"}))
            | (
                (TripChatMessage.status == "completed")
                & TripChatMessage.intent.in_({"create_plan", "regenerate_plan"})
            )
        )
        now = datetime.now(UTC)
        result = self.db.execute(
            update(PreferenceObservationJob)
            .where(
                PreferenceObservationJob.status == "queued",
                PreferenceObservationJob.message_id.in_(terminal_message_ids),
            )
            .values(status="skipped", completed_at=now, updated_at=now)
        )
        self.db.commit()
        return result.rowcount or 0

    def load_message_and_chat(
        self,
        job: PreferenceObservationJob,
    ) -> tuple[TripChatMessage, TripChat] | None:
        row = self.db.execute(
            select(TripChatMessage, TripChat)
            .join(TripChat, TripChat.id == TripChatMessage.chat_id)
            .where(
                TripChatMessage.id == job.message_id,
                TripChat.user_id == job.user_id,
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def complete(self, job: PreferenceObservationJob) -> None:
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.error_code = None
        job.error_message = None
        job.updated_at = datetime.now(UTC)

    def retry_or_fail(
        self,
        job_id: str,
        *,
        max_attempts: int,
        code: str,
        message: str,
    ) -> None:
        job = self.db.get(PreferenceObservationJob, job_id)
        if job is None:
            return
        job.status = "failed" if job.attempts >= max_attempts else "queued"
        job.started_at = None
        job.error_code = code
        job.error_message = message[:500]
        job.updated_at = datetime.now(UTC)
        self.db.commit()
