import asyncio
import json
import logging
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.plans.chat_model import TripChatMessage
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_service import TripChatService
from app.modules.plans.destination_inference import (
    infer_destination_from_urls,
    usable_destination,
)
from app.modules.plans.dependencies import get_plan_mutation_service, get_plan_service
from app.modules.plans.url_job_model import UrlImportJob
from app.modules.plans.url_job_repository import UrlImportJobRepository
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.users.model import User
from app.shared.errors import AppError


logger = logging.getLogger(__name__)
terminal_logger = logging.getLogger("uvicorn.error")


class UrlImportJobWorker:
    """Persistent FIFO runner for URL and OCR-image sources."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        poll_interval_seconds: float = 0.75,
        job_timeout_seconds: float | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds
        self.job_timeout_seconds = (
            job_timeout_seconds or settings.url_import_job_timeout_seconds
        )
        self._active_job_id: str | None = None
        self._active_process_task: asyncio.Task[int] | None = None
        self._active_completion: asyncio.Event | None = None
        self._active_tasks: dict[str, asyncio.Task[int]] = {}
        self._active_completions: dict[str, asyncio.Event] = {}
        self._cancel_requested_job_ids: set[str] = set()

    def recover_interrupted(self) -> int:
        with self.session_factory() as db:
            return UrlImportJobRepository(db).recover_interrupted()

    async def run_forever(self) -> None:
        recovered = self.recover_interrupted()
        if recovered:
            logger.info("Requeued %s interrupted URL import jobs", recovered)
        slots = [
            asyncio.create_task(
                self._run_slot(),
                name=f"url-import-worker-slot-{index + 1}",
            )
            for index in range(settings.url_import_worker_concurrency)
        ]
        try:
            await asyncio.gather(*slots)
        finally:
            for slot in slots:
                slot.cancel()

    async def _run_slot(self) -> None:
        while True:
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A terminal-state write should not be able to kill the FIFO
                # worker permanently. The next iteration uses a fresh session
                # and can reconcile stale running rows.
                logger.exception("URL import worker iteration failed")
                await asyncio.sleep(self.poll_interval_seconds)
                continue
            if not processed:
                await asyncio.sleep(self.poll_interval_seconds)

    async def cancel(self, job_id: str) -> bool:
        """Cancel the active job and wait until its row releases the FIFO queue."""
        task = self._active_tasks.get(job_id)
        completion = self._active_completions.get(job_id)
        if (
            task is None
            or completion is None
            or task.done()
        ):
            return False
        self._cancel_requested_job_ids.add(job_id)
        task.cancel()
        await completion.wait()
        return True

    async def run_once(self) -> bool:
        with self.session_factory() as db:
            repository = UrlImportJobRepository(db)
            expired = repository.fail_stale_running(
                timeout_seconds=self.job_timeout_seconds
            )
            if expired:
                logger.warning("Failed %s stale URL import jobs", expired)
            job = repository.claim_next(
                max_concurrency=settings.url_import_worker_concurrency
            )
            if job is None:
                return False
            job_id = job.id
            processing_started_at = time.perf_counter()
            process_task = asyncio.create_task(
                self._process(db, job_id),
                name=f"url-import-job-{job_id}",
            )
            completion = asyncio.Event()
            self._active_job_id = job_id
            self._active_process_task = process_task
            self._active_completion = completion
            self._active_tasks[job_id] = process_task
            self._active_completions[job_id] = completion
            try:
                revision = await asyncio.wait_for(
                    process_task,
                    timeout=self.job_timeout_seconds,
                )
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                worker_is_stopping = bool(
                    current_task is not None and current_task.cancelling()
                )
                if (
                    worker_is_stopping
                    or job_id not in self._cancel_requested_job_ids
                ):
                    raise
                db.rollback()
                repository.delete_running(job_id)
            except TimeoutError:
                db.rollback()
                message = (
                    "Tác vụ trích xuất đã quá thời gian cho phép. "
                    "Hãy thử lại URL này."
                )
                if job.import_kind == "explorer_job":
                    repository.fail_batch(
                        job.batch_id, code="URL_IMPORT_TIMEOUT", message=message
                    )
                else:
                    repository.fail(job_id, code="URL_IMPORT_TIMEOUT", message=message)
            except AppError as exc:
                db.rollback()
                current_job = db.get(UrlImportJob, job_id)
                if (
                    current_job is not None
                    and current_job.import_kind == "trip_intent_plan_job"
                    and exc.code in {"TRIP_INTENT_SUPERSEDED", "VERSION_CONFLICT"}
                ):
                    repository.requeue_superseded(job_id)
                else:
                    if job.import_kind == "explorer_job":
                        repository.fail_batch(
                            job.batch_id, code=exc.code, message=exc.message
                        )
                    else:
                        repository.fail(job_id, code=exc.code, message=exc.message)
            except Exception:
                logger.exception("URL import job %s failed", job_id)
                db.rollback()
                message = "Không thể trích xuất URL này. Bạn có thể thử lại riêng tác vụ."
                if job.import_kind == "explorer_job":
                    repository.fail_batch(
                        job.batch_id, code="URL_IMPORT_FAILED", message=message
                    )
                else:
                    repository.fail(job_id, code="URL_IMPORT_FAILED", message=message)
            else:
                if job.import_kind == "explorer_job":
                    repository.succeed_batch(job.batch_id, revision=revision)
                else:
                    repository.succeed(job_id, revision)
            finally:
                self._log_terminal_timing(
                    db,
                    job_id=job_id,
                    processing_started_at=processing_started_at,
                )
                self._cancel_requested_job_ids.discard(job_id)
                if self._active_job_id == job_id:
                    self._active_job_id = None
                    self._active_process_task = None
                    self._active_completion = None
                self._active_tasks.pop(job_id, None)
                self._active_completions.pop(job_id, None)
                completion.set()
            return True

    @staticmethod
    def _log_terminal_timing(
        db: Session,
        *,
        job_id: str,
        processing_started_at: float,
    ) -> None:
        """Log one privacy-safe end-to-end summary for a terminal URL job."""
        try:
            job = db.get(UrlImportJob, job_id)
            if job is None:
                return
            if job.status in {"queued", "running"}:
                # The application may be shutting down while the task is
                # still resumable; do not present that as a terminal result.
                return
            processing_seconds = round(
                max(0.0, time.perf_counter() - processing_started_at),
                3,
            )
            explorer_seconds = _timing_total_seconds(job.explorer_timing)
            planner_seconds = _timing_total_seconds(job.planner_timing)
            queue_wait_seconds = None
            if job.created_at is not None and job.started_at is not None:
                queue_wait_seconds = round(
                    max(
                        0.0,
                        (job.started_at - job.created_at).total_seconds(),
                    ),
                    3,
                )
            accounted_seconds = round(
                (explorer_seconds or 0.0) + (planner_seconds or 0.0),
                3,
            )
            terminal_logger.info(
                "VSF_TIMING url_job %s",
                json.dumps(
                    {
                        "event": "url_job_timing",
                        "jobId": job_id,
                        "sourceType": job.source_type,
                        "status": job.status,
                        "attemptCount": job.attempt_count,
                        "queueWaitSeconds": queue_wait_seconds,
                        "processingWallSeconds": processing_seconds,
                        "explorerSeconds": explorer_seconds,
                        "plannerSeconds": planner_seconds,
                        "accountedSeconds": accounted_seconds,
                        "orchestrationOverheadSeconds": round(
                            max(0.0, processing_seconds - accounted_seconds),
                            3,
                        ),
                        "errorCode": job.error_code,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        except Exception:
            logger.warning(
                "Could not emit terminal timing for URL import job %s.",
                job_id,
                exc_info=True,
            )

    async def _process(self, db: Session, job_id: str) -> int:
        job = db.get(UrlImportJob, job_id)
        if job is None:
            raise AppError(404, "URL_IMPORT_JOB_NOT_FOUND", "Không tìm thấy tác vụ nguồn.")
        if job.import_kind == "trip_intent_plan_job":
            return await self._process_trip_intent_plan(db, job)
        if job.import_kind != "explorer_job":
            raise AppError(404, "URL_IMPORT_JOB_NOT_FOUND", "Không tìm thấy tác vụ nguồn.")
        user = db.get(User, job.user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng của tác vụ.")

        batch_jobs = (
            list(db.scalars(
                select(UrlImportJob).where(
                    UrlImportJob.import_kind == "explorer_job",
                    UrlImportJob.batch_id == job.batch_id,
                    UrlImportJob.processing_status.in_(("queued", "running")),
                ).order_by(UrlImportJob.batch_position.asc())
            ))
            if job.batch_id
            else [job]
        )
        # A normal chat edit can finish while extraction is running. Reload and
        # retry the final workflow against the newest revision instead of
        # dropping either update.
        last_conflict: AppError | None = None
        for _ in range(3):
            UrlImportJobRepository(db).mark_exploring(job_id)
            chat_repository = TripChatRepository(db)
            chat = chat_repository.get(job.chat_id, job.user_id)
            service = TripChatService(
                chat_repository,
                get_plan_service(db),
                get_plan_mutation_service(db),
            )
            image_jobs = [item for item in batch_jobs if item.source_type == "image"]
            url_jobs = [item for item in batch_jobs if item.source_type != "image"]
            urls = [item.url for item in url_jobs if item.url]
            content = "\n".join(
                value for value in [job.request_content, *urls] if value
            ).strip()
            images = [
                    ImageUploadPayload(
                        file_name=item.source_name or "uploaded-image",
                        mime_type=item.image_mime_type,
                        data=bytes(item.image_data or b""),
                    )
                    for item in image_jobs
                ]
            if any(not item.image_data for item in image_jobs):
                raise AppError(
                    422,
                    "IMAGE_DATA_MISSING",
                    "Không còn dữ liệu ảnh để xử lý. Hãy tải ảnh lên lại.",
                )
            try:
                result = await service.amend(
                    job.chat_id,
                    user,
                    content=content,
                    expected_revision=chat.revision,
                    initial_destination=(
                        usable_destination(chat.destination)
                        or (infer_destination_from_urls(urls) if urls else None)
                        or "unspecified"
                    ),
                    urls=urls,
                    images=images,
                    force_url_refresh=any(item.force_refresh for item in batch_jobs),
                    turn_id=(
                        job.batch_id
                        if job.batch_id and db.get(TripChatMessage, job.batch_id)
                        else None
                    ),
                    on_explore_complete=lambda timing: UrlImportJobRepository(db).mark_planning(
                        job_id,
                        explorer_timing=(
                            timing.model_dump(mode="json", by_alias=True)
                            if timing is not None
                            else None
                        ),
                    ),
                    on_planner_timing=lambda timing: UrlImportJobRepository(db).mark_planner_timing(
                        job_id,
                        planner_timing=timing.model_dump(mode="json", by_alias=True),
                    ),
                )
                return result.revision
            except AppError as exc:
                if exc.code != "VERSION_CONFLICT":
                    raise
                db.rollback()
                db.expire_all()
                last_conflict = exc
        raise last_conflict or AppError(
            409,
            "VERSION_CONFLICT",
            "Lịch trình liên tục thay đổi trong khi xử lý URL. Hãy thử lại tác vụ.",
        )

    async def _process_trip_intent_plan(
        self,
        db: Session,
        job: UrlImportJob,
    ) -> int:
        user = db.get(User, job.user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng của tác vụ.")
        chat_repository = TripChatRepository(db)
        chat = chat_repository.get(job.chat_id, job.user_id)
        trip_intent = chat_repository.load_trip_intent(chat)
        if trip_intent is None or chat.current_plan is None:
            raise AppError(
                409,
                "TRIP_INTENT_NOT_READY",
                "Không có thông tin chuyến đi và plan hiện hành để đồng bộ.",
            )
        intent_version = chat.trip_intent_version
        service = TripChatService(
            chat_repository,
            get_plan_service(db),
            get_plan_mutation_service(db),
        )
        result = await service.regenerate_trip_intent_plan(
            chat.id,
            user,
            trip_intent=trip_intent,
            expected_revision=chat.revision,
            expected_trip_intent_version=intent_version,
        )
        return result.revision


def _timing_total_seconds(value: object) -> float | None:
    if not isinstance(value, dict):
        return None
    raw_total = value.get("totalSeconds")
    if not isinstance(raw_total, (int, float)):
        return None
    return round(max(0.0, float(raw_total)), 3)
