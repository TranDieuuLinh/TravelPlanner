from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.plans.chat_model import TripChat, TripChatMessage
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.url_job_model import UrlImportJob
from app.modules.plans.url_job_schema import UrlImportJobRead
from app.shared.errors import AppError


ACTIVE_JOB_STATUSES = ("queued", "running")


class UrlImportJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        chat_id: str,
        user_id: int,
        expected_revision: int,
        urls: list[str],
        request_content: str,
        display_content: str,
        force_refresh: bool = False,
    ) -> list[UrlImportJob]:
        chat = self.db.scalar(
            select(TripChat).where(
                TripChat.id == chat_id,
                TripChat.user_id == user_id,
            )
        )
        if chat is None:
            raise AppError(404, "TRIP_CHAT_NOT_FOUND", "Không tìm thấy cuộc trò chuyện chuyến đi.")
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi gửi.",
            )
        batch_id = str(uuid4())
        turn = TripChatRepository(self.db).create_turn(
            chat,
            client_turn_id=f"url-batch-{batch_id}",
            content=display_content,
            attachment_names=[],
            expected_revision=expected_revision,
            commit=False,
        )
        batch_id = turn.lifecycle_id
        jobs = [
            UrlImportJob(
                id=str(uuid4()),
                import_kind="explorer_job",
                batch_id=batch_id,
                user_id=user_id,
                chat_id=chat_id,
                url=url,
                source_label=url,
                request_content=request_content,
                schema_version="explorer-place-proposal-v1",
                ontology_version="knowledge-graph-v2",
                dataset_hash="",
                force_refresh=force_refresh,
                batch_position=batch_position,
                processing_status="queued",
                processing_phase="queued",
                review_status="not_required",
                status="queued",
            )
            for batch_position, url in enumerate(urls)
        ]
        self.db.add_all(jobs)
        self.db.commit()
        for job in jobs:
            self.db.refresh(job)
        return jobs

    def enqueue_images(
        self,
        *,
        chat_id: str,
        user_id: int,
        expected_revision: int,
        images: list[tuple[str, str, bytes]],
        request_content: str,
    ) -> list[UrlImportJob]:
        chat = self.db.scalar(
            select(TripChat).where(
                TripChat.id == chat_id,
                TripChat.user_id == user_id,
            )
        )
        if chat is None:
            raise AppError(404, "TRIP_CHAT_NOT_FOUND", "Không tìm thấy cuộc trò chuyện chuyến đi.")
        if chat.revision != expected_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi gửi.",
            )
        batch_id = str(uuid4())
        turn = TripChatRepository(self.db).create_turn(
            chat,
            client_turn_id=f"image-batch-{batch_id}",
            content=request_content,
            attachment_names=[file_name for file_name, _, _ in images],
            expected_revision=expected_revision,
            commit=False,
        )
        batch_id = turn.lifecycle_id
        jobs = [
            UrlImportJob(
                id=str(uuid4()),
                import_kind="explorer_job",
                batch_id=batch_id,
                user_id=user_id,
                chat_id=chat_id,
                source_type="image",
                url="",
                source_name=file_name,
                source_label=file_name,
                image_mime_type=mime_type,
                image_data=data,
                request_content=request_content,
                schema_version="explorer-place-proposal-v1",
                ontology_version="knowledge-graph-v2",
                dataset_hash="",
                force_refresh=False,
                batch_position=batch_position,
                processing_status="queued",
                processing_phase="queued",
                review_status="not_required",
                status="queued",
            )
            for batch_position, (file_name, mime_type, data) in enumerate(images)
        ]
        self.db.add_all(jobs)
        self.db.commit()
        for job in jobs:
            self.db.refresh(job)
        return jobs

    def list_for_user(self, user_id: int, *, limit: int = 40) -> list[UrlImportJob]:
        active_first = case(
            (UrlImportJob.processing_status == "running", 0),
            (UrlImportJob.processing_status == "queued", 1),
            else_=2,
        )
        statement = (
            select(UrlImportJob)
            .where(
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.user_id == user_id,
            )
            .order_by(active_first, UrlImportJob.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement))

    def get_for_user(self, job_id: str, user_id: int) -> UrlImportJob:
        job = self.db.scalar(
            select(UrlImportJob).where(
                UrlImportJob.id == job_id,
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.user_id == user_id,
            )
        )
        if job is None:
            raise AppError(404, "URL_IMPORT_JOB_NOT_FOUND", "Không tìm thấy tác vụ nguồn.")
        return job

    def recover_interrupted(self) -> int:
        batch_ids = list(
            self.db.scalars(
                select(UrlImportJob.batch_id)
                .where(
                    UrlImportJob.import_kind == "explorer_job",
                    UrlImportJob.processing_status == "running",
                    UrlImportJob.batch_id.is_not(None),
                )
                .distinct()
            )
        )
        result = self.db.execute(
            update(UrlImportJob)
            .where(
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.processing_status == "running",
            )
            .values(
                processing_status="queued", status="queued", started_at=None,
                processing_phase="queued",
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        self.db.flush()
        for batch_id in batch_ids:
            self._set_batch_turn_status(batch_id, "queued")
        self.db.commit()
        return result.rowcount or 0

    def fail_stale_running(self, *, timeout_seconds: float) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        stale_filter = (
            (UrlImportJob.processing_status == "running")
            & (UrlImportJob.import_kind == "explorer_job")
            & (
                (UrlImportJob.started_at.is_(None))
                | (UrlImportJob.started_at <= cutoff)
            )
        )
        batch_ids = list(
            self.db.scalars(
                select(UrlImportJob.batch_id)
                .where(stale_filter, UrlImportJob.batch_id.is_not(None))
                .distinct()
            )
        )
        result = self.db.execute(
            update(UrlImportJob)
            .where(stale_filter)
            .values(
                processing_status="failed",
                processing_phase="complete",
                status="failed",
                error_code="URL_IMPORT_TIMEOUT",
                error_message=(
                    "Tác vụ trích xuất đã quá thời gian cho phép. "
                    "Hãy thử lại URL này."
                ),
                finished_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        self.db.flush()
        for batch_id in batch_ids:
            self._sync_batch_turn(batch_id)
        self.db.commit()
        return result.rowcount or 0

    def claim_next(self) -> UrlImportJob | None:
        running_count = self.db.scalar(
            select(func.count()).select_from(UrlImportJob).where(
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.processing_status == "running"
            )
        )
        if running_count:
            return None
        statement = (
            select(UrlImportJob)
            .where(
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.processing_status == "queued",
            )
            .order_by(
                UrlImportJob.created_at.asc(),
                UrlImportJob.batch_position.asc(),
                UrlImportJob.id.asc(),
            )
            .limit(1)
        )
        if self.db.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = self.db.scalar(statement)
        if job is None:
            return None
        job.processing_status = "running"
        job.processing_phase = "exploring"
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        job.error_code = None
        job.error_message = None
        job.attempt_count += 1
        self._set_batch_turn_status(job.batch_id, "executing")
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_exploring(self, job_id: str) -> None:
        job = self.db.get(UrlImportJob, job_id)
        if job is None or job.processing_status != "running":
            return
        job.processing_phase = "exploring"
        job.explorer_timing = None
        self.db.commit()

    def mark_planning(
        self,
        job_id: str,
        *,
        explorer_timing: dict | None,
    ) -> None:
        job = self.db.get(UrlImportJob, job_id)
        if job is None or job.processing_status != "running":
            return
        job.processing_phase = "planning"
        job.explorer_timing = explorer_timing
        self.db.commit()

    def succeed(self, job_id: str, revision: int) -> None:
        job = self.db.get(UrlImportJob, job_id)
        if job is None:
            return
        chat = self.db.get(TripChat, job.chat_id)
        job.processing_status = "succeeded"
        job.processing_phase = "complete"
        job.status = "succeeded"
        job.result_revision = revision
        job.explorer_timing = (
            chat.latest_explorer_timing if chat is not None else None
        )
        job.planner_timing = (
            chat.latest_planner_timing if chat is not None else None
        )
        job.finished_at = datetime.now(UTC)
        self.db.flush()
        self._sync_batch_turn(job.batch_id, revision=revision)
        self.db.commit()

    def fail(self, job_id: str, *, code: str, message: str) -> None:
        job = self.db.get(UrlImportJob, job_id)
        if job is None:
            return
        job.processing_status = "failed"
        job.processing_phase = "complete"
        job.status = "failed"
        job.error_code = code[:64]
        job.error_message = message[:1000]
        job.finished_at = datetime.now(UTC)
        self.db.flush()
        self._sync_batch_turn(job.batch_id)
        self.db.commit()

    def retry(self, job_id: str, user_id: int) -> UrlImportJob:
        job = self.get_for_user(job_id, user_id)
        if job.status != "failed":
            raise AppError(409, "URL_IMPORT_JOB_NOT_FAILED", "Chỉ có thể thử lại tác vụ đã thất bại.")
        # A failed run restarts from its original URL or persisted image bytes.
        job.force_refresh = True
        job.processing_status = "queued"
        job.processing_phase = "queued"
        job.status = "queued"
        job.started_at = None
        job.finished_at = None
        job.error_code = None
        job.error_message = None
        job.explorer_timing = None
        job.planner_timing = None
        self._set_batch_turn_status(job.batch_id, "queued")
        self.db.commit()
        self.db.refresh(job)
        return job

    def reprocess(self, job_id: str, user_id: int) -> UrlImportJob:
        source_job = self.get_for_user(job_id, user_id)
        if source_job.status not in {"succeeded", "failed"}:
            raise AppError(
                409,
                "URL_IMPORT_JOB_NOT_FINISHED",
                "Chỉ có thể phân tích lại tác vụ đã kết thúc.",
                details={"status": source_job.status},
            )
        job = UrlImportJob(
            id=str(uuid4()),
            import_kind="explorer_job",
            batch_id=str(uuid4()),
            user_id=source_job.user_id,
            chat_id=source_job.chat_id,
            source_type=source_job.source_type,
            url=source_job.url,
            source_name=source_job.source_name,
            source_label=source_job.source_label,
            image_mime_type=source_job.image_mime_type,
            image_data=source_job.image_data,
            request_content=source_job.request_content,
            schema_version="explorer-place-proposal-v1",
            ontology_version="knowledge-graph-v2",
            dataset_hash="",
            # "Run again" is a full replay: URL jobs bypass extraction cache
            # and image jobs retain their original bytes so OCR runs again.
            force_refresh=True,
            batch_position=0,
            processing_status="queued",
            processing_phase="queued",
            review_status="not_required",
            status="queued",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def delete_queued(self, job_id: str, user_id: int) -> None:
        job = self.get_for_user(job_id, user_id)
        batch_id = job.batch_id
        result = self.db.execute(
            delete(UrlImportJob).where(
                UrlImportJob.id == job_id,
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.user_id == user_id,
                UrlImportJob.processing_status == "queued",
            )
        )
        if result.rowcount:
            self.db.flush()
            self._sync_batch_turn(batch_id)
            self.db.commit()
            return

        raise AppError(
            409,
            "URL_IMPORT_JOB_NOT_QUEUED",
            "Chỉ có thể xóa nguồn đang chờ.",
            details={"status": job.status},
        )

    def delete_running(self, job_id: str) -> bool:
        """Delete a job only after its in-process task has been cancelled."""
        job = self.db.get(UrlImportJob, job_id)
        batch_id = job.batch_id if job is not None else None
        result = self.db.execute(
            delete(UrlImportJob).where(
                UrlImportJob.id == job_id,
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.processing_status == "running",
            )
        )
        self.db.flush()
        if result.rowcount:
            self._sync_batch_turn(batch_id)
        self.db.commit()
        return bool(result.rowcount)

    def delete_terminal(self, job_id: str, user_id: int) -> None:
        result = self.db.execute(
            delete(UrlImportJob).where(
                UrlImportJob.id == job_id,
                UrlImportJob.import_kind == "explorer_job",
                UrlImportJob.user_id == user_id,
                UrlImportJob.processing_status.in_(("succeeded", "failed")),
            )
        )
        if result.rowcount:
            self.db.commit()
            return

        job = self.get_for_user(job_id, user_id)
        raise AppError(
            409,
            "URL_IMPORT_JOB_NOT_FINISHED",
            "Chỉ có thể xóa tác vụ đã hoàn tất hoặc thất bại.",
            details={"status": job.status},
        )

    def read(self, job: UrlImportJob) -> UrlImportJobRead:
        position: int | None = None
        if job.status == "queued":
            queued_ids = list(
                self.db.scalars(
                    select(UrlImportJob.id)
                    .where(
                        UrlImportJob.import_kind == "explorer_job",
                        UrlImportJob.processing_status == "queued",
                    )
                    .order_by(
                        UrlImportJob.created_at.asc(),
                        UrlImportJob.batch_position.asc(),
                        UrlImportJob.id.asc(),
                    )
                )
            )
            position = queued_ids.index(job.id) + 1
        return UrlImportJobRead(
            id=job.id,
            chatId=job.chat_id,
            sourceType=job.source_type,
            sourceLabel=job.source_name or job.url,
            url=job.url,
            forceRefresh=job.force_refresh,
            status=job.status,
            phase=job.processing_phase,
            queuePosition=position,
            attemptCount=job.attempt_count,
            resultRevision=job.result_revision,
            errorCode=job.error_code,
            errorMessage=job.error_message,
            explorerTiming=job.explorer_timing,
            plannerTiming=job.planner_timing,
            createdAt=job.created_at,
            startedAt=job.started_at,
            finishedAt=job.finished_at,
        )

    def _batch_turn(self, batch_id: str | None) -> TripChatMessage | None:
        if not batch_id:
            return None
        return self.db.scalar(
            select(TripChatMessage).where(
                TripChatMessage.id == batch_id,
                TripChatMessage.message_kind == "turn_request",
            )
        )

    def _set_batch_turn_status(self, batch_id: str | None, status: str) -> None:
        turn = self._batch_turn(batch_id)
        if turn is None:
            return
        turn.status = status
        if status in ACTIVE_JOB_STATUSES or status == "executing":
            turn.error_code = None
            turn.error_message = None
        turn.updated_at = datetime.now(UTC)

    def _sync_batch_turn(
        self,
        batch_id: str | None,
        *,
        revision: int | None = None,
    ) -> None:
        turn = self._batch_turn(batch_id)
        if turn is None:
            return
        sibling_statuses = list(
            self.db.scalars(
                select(UrlImportJob.processing_status).where(
                    UrlImportJob.import_kind == "explorer_job",
                    UrlImportJob.batch_id == batch_id,
                )
            )
        )
        if not sibling_statuses:
            turn.status = "cancelled"
        elif any(status in ACTIVE_JOB_STATUSES for status in sibling_statuses):
            turn.status = "executing"
        elif any(status == "failed" for status in sibling_statuses):
            turn.status = "failed"
            turn.error_code = "URL_IMPORT_BATCH_FAILED"
            turn.error_message = "Có nguồn không thể xử lý. Bạn có thể chạy lại nguồn bị lỗi."
        else:
            turn.status = "completed"
            if revision is not None:
                turn.plan_revision = revision
                turn.result_summary = {"planRevision": revision}
        turn.updated_at = datetime.now(UTC)
