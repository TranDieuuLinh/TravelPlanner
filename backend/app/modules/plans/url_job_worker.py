import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
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
        self._cancel_requested_job_ids: set[str] = set()

    def recover_interrupted(self) -> int:
        with self.session_factory() as db:
            return UrlImportJobRepository(db).recover_interrupted()

    async def run_forever(self) -> None:
        recovered = self.recover_interrupted()
        if recovered:
            logger.info("Requeued %s interrupted URL import jobs", recovered)
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
        task = self._active_process_task
        completion = self._active_completion
        if (
            self._active_job_id != job_id
            or task is None
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
            job = repository.claim_next()
            if job is None:
                return False
            job_id = job.id
            process_task = asyncio.create_task(
                self._process(db, job_id),
                name=f"url-import-job-{job_id}",
            )
            completion = asyncio.Event()
            self._active_job_id = job_id
            self._active_process_task = process_task
            self._active_completion = completion
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
                repository.fail(
                    job_id,
                    code="URL_IMPORT_TIMEOUT",
                    message=(
                        "Tác vụ trích xuất đã quá thời gian cho phép. "
                        "Hãy thử lại URL này."
                    ),
                )
            except AppError as exc:
                db.rollback()
                repository.fail(job_id, code=exc.code, message=exc.message)
            except Exception:
                logger.exception("URL import job %s failed", job_id)
                db.rollback()
                repository.fail(
                    job_id,
                    code="URL_IMPORT_FAILED",
                    message="Không thể trích xuất URL này. Bạn có thể thử lại riêng tác vụ.",
                )
            else:
                repository.succeed(job_id, revision)
            finally:
                self._cancel_requested_job_ids.discard(job_id)
                if self._active_job_id == job_id:
                    self._active_job_id = None
                    self._active_process_task = None
                    self._active_completion = None
                completion.set()
            return True

    async def _process(self, db: Session, job_id: str) -> int:
        job = db.get(UrlImportJob, job_id)
        if job is None:
            raise AppError(404, "URL_IMPORT_JOB_NOT_FOUND", "Không tìm thấy tác vụ nguồn.")
        if job.import_kind != "explorer_job":
            raise AppError(404, "URL_IMPORT_JOB_NOT_FOUND", "Không tìm thấy tác vụ nguồn.")
        user = db.get(User, job.user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng của tác vụ.")

        # A normal chat edit can finish while extraction is running. Reload and
        # retry the final workflow against the newest revision instead of
        # dropping either update.
        last_conflict: AppError | None = None
        for _ in range(3):
            chat_repository = TripChatRepository(db)
            chat = chat_repository.get(job.chat_id, job.user_id)
            service = TripChatService(
                chat_repository,
                get_plan_service(db),
                get_plan_mutation_service(db),
            )
            is_image = job.source_type == "image"
            content = (
                job.request_content
                if is_image
                else f"{job.request_content}\n{job.url}".strip()
            )
            images = (
                [
                    ImageUploadPayload(
                        file_name=job.source_name or "uploaded-image",
                        mime_type=job.image_mime_type,
                        data=bytes(job.image_data or b""),
                    )
                ]
                if is_image
                else []
            )
            if is_image and not job.image_data:
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
                        or (infer_destination_from_urls([job.url]) if job.url else None)
                        or "unspecified"
                    ),
                    urls=[] if is_image else [job.url],
                    images=images,
                    force_url_refresh=job.force_refresh,
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
