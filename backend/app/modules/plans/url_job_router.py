import ipaddress
import re
from pathlib import PurePath
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.plans.url_job_repository import UrlImportJobRepository
from app.modules.plans.url_job_schema import UrlImportJobBatchRead, UrlImportJobRead
from app.modules.plans.explorer.tools.image_ocr import SUPPORTED_IMAGE_MIME_TYPES
from app.modules.users.model import User
from app.shared.errors import AppError


router = APIRouter(tags=["url-import-jobs"])
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _validated_urls(content: str, explicit_urls: list[str]) -> list[str]:
    values = [*explicit_urls, *URL_PATTERN.findall(content)]
    urls: list[str] = []
    for value in values:
        cleaned = value.strip().rstrip(".,;:!?)]}")
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AppError(422, "INVALID_URL", "URL phải dùng http hoặc https và có tên miền hợp lệ.")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".localhost"):
            raise AppError(422, "UNSAFE_URL", "Không thể nhập URL mạng nội bộ.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise AppError(422, "UNSAFE_URL", "Không thể nhập URL mạng nội bộ.")
        if cleaned not in urls:
            urls.append(cleaned)
    if not urls:
        raise AppError(422, "URL_REQUIRED", "Hãy dán ít nhất một URL hợp lệ.")
    if len(urls) > 20:
        raise AppError(422, "TOO_MANY_URLS", "Mỗi lần chỉ có thể thêm tối đa 20 URL.")
    return urls


@router.post(
    "/trip-chats/{chat_id}/url-jobs",
    response_model=UrlImportJobBatchRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_url_jobs(
    chat_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_csrf)],
    content: Annotated[str, Form(min_length=1, max_length=10_000)],
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    urls: Annotated[list[str] | None, Form()] = None,
    force_refresh: Annotated[bool, Form(alias="forceRefresh")] = False,
) -> UrlImportJobBatchRead:
    normalized_urls = _validated_urls(content, urls or [])
    request_content = URL_PATTERN.sub(" ", content).strip()
    repository = UrlImportJobRepository(db)
    jobs = repository.enqueue(
        chat_id=chat_id,
        user_id=current_user.id,
        expected_revision=expected_revision,
        urls=normalized_urls,
        request_content=request_content,
        display_content=content.strip(),
        force_refresh=force_refresh,
    )
    return UrlImportJobBatchRead(jobs=[repository.read(job) for job in jobs])


@router.post(
    "/trip-chats/{chat_id}/image-jobs",
    response_model=UrlImportJobBatchRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_image_jobs(
    chat_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_csrf)],
    content: Annotated[str, Form(min_length=1, max_length=10_000)],
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    images: Annotated[list[UploadFile], File()],
) -> UrlImportJobBatchRead:
    if not images:
        raise AppError(422, "IMAGE_REQUIRED", "Hãy đính kèm ít nhất một ảnh.")
    if len(images) > 20:
        raise AppError(422, "TOO_MANY_IMAGES", "Mỗi lần chỉ có thể thêm tối đa 20 ảnh.")

    payloads: list[tuple[str, str, bytes]] = []
    try:
        for image in images:
            mime_type = (image.content_type or "application/octet-stream").lower()
            if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
                raise AppError(
                    422,
                    "UNSUPPORTED_IMAGE_TYPE",
                    "Chỉ hỗ trợ ảnh JPEG, PNG, WebP, HEIC và HEIF.",
                )
            data = await image.read(settings.user_post_image_max_bytes + 1)
            if not data:
                raise AppError(422, "EMPTY_IMAGE", "Ảnh tải lên không có dữ liệu.")
            if len(data) > settings.user_post_image_max_bytes:
                raise AppError(
                    413,
                    "IMAGE_TOO_LARGE",
                    f"Mỗi ảnh phải nhỏ hơn {settings.user_post_image_max_bytes // (1024 * 1024)} MB.",
                )
            file_name = PurePath(image.filename or "uploaded-image").name[:255]
            payloads.append((file_name, mime_type, data))
    finally:
        for image in images:
            await image.close()

    repository = UrlImportJobRepository(db)
    jobs = repository.enqueue_images(
        chat_id=chat_id,
        user_id=current_user.id,
        expected_revision=expected_revision,
        images=payloads,
        request_content=content.strip(),
    )
    return UrlImportJobBatchRead(jobs=[repository.read(job) for job in jobs])


@router.get("/url-import-jobs", response_model=UrlImportJobBatchRead)
def list_url_jobs(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UrlImportJobBatchRead:
    repository = UrlImportJobRepository(db)
    jobs = repository.list_for_user(current_user.id)
    return UrlImportJobBatchRead(jobs=[repository.read(job) for job in jobs])


@router.post(
    "/url-import-jobs/{job_id}/retry",
    response_model=UrlImportJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_url_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> UrlImportJobRead:
    repository = UrlImportJobRepository(db)
    return repository.read(repository.retry(job_id, current_user.id))


@router.post(
    "/url-import-jobs/{job_id}/reprocess",
    response_model=UrlImportJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_url_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> UrlImportJobRead:
    repository = UrlImportJobRepository(db)
    return repository.read(repository.reprocess(job_id, current_user.id))


@router.delete(
    "/url-import-jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_url_job(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> None:
    repository = UrlImportJobRepository(db)
    job = repository.get_for_user(job_id, current_user.id)
    if job.status == "queued":
        repository.delete_queued(job_id, current_user.id)
        return
    if job.status == "running":
        worker = getattr(request.app.state, "url_import_worker", None)
        if worker is not None and await worker.cancel(job_id):
            return
        db.expire_all()
        current = repository.get_for_user(job_id, current_user.id)
        raise AppError(
            409,
            "URL_IMPORT_JOB_NOT_CANCELLABLE",
            "Tác vụ vừa hoàn tất hoặc không còn chạy trong worker này.",
            details={"status": current.status},
        )
    repository.delete_terminal(job_id, current_user.id)
