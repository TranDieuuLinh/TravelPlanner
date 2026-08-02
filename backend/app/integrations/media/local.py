from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, status

from app.shared.errors import AppError
from app.integrations.media.base import StoredPostMedia


class LocalPostMediaStorage:
    """Local MVP adapter for the PostMediaStorage contract."""

    _image_extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    _video_extensions = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
    }

    def __init__(
        self,
        root: Path,
        *,
        image_max_bytes: int,
        video_max_bytes: int,
    ) -> None:
        self.root = root
        self.image_max_bytes = image_max_bytes
        self.video_max_bytes = video_max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, *, content_type: str) -> StoredPostMedia:
        declared_type = (upload.content_type or "").lower()
        allowed = self._image_extensions if content_type == "post" else self._video_extensions
        max_bytes = self.image_max_bytes if content_type == "post" else self.video_max_bytes
        extension = allowed.get(declared_type)
        if not extension:
            await upload.close()
            expected = "ảnh JPEG, PNG hoặc WebP" if content_type == "post" else "video MP4, WebM hoặc MOV"
            raise AppError(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "POST_MEDIA_TYPE_UNSUPPORTED",
                f"Vui lòng chọn {expected}.",
            )

        token = uuid4().hex
        filename = f"{token}{extension}"
        temporary_path = self.root / f".{token}.upload"
        size_bytes = 0
        try:
            first_chunk = await upload.read(1024 * 1024)
            if not first_chunk or not self._signature_matches(first_chunk[:16], declared_type):
                raise AppError(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    "POST_MEDIA_INVALID",
                    "Nội dung tệp không khớp với định dạng ảnh hoặc video đã khai báo.",
                )
            with temporary_path.open("xb") as output:
                chunk = first_chunk
                while chunk:
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        limit_mb = max_bytes // (1024 * 1024)
                        raise AppError(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "POST_MEDIA_TOO_LARGE",
                            f"Tệp vượt quá giới hạn {limit_mb} MB.",
                        )
                    output.write(chunk)
                    chunk = await upload.read(1024 * 1024)
            temporary_path.replace(self.root / filename)
            return StoredPostMedia(filename, declared_type, size_bytes)
        except Exception:
            if temporary_path.is_file():
                temporary_path.unlink()
            raise
        finally:
            await upload.close()

    def delete(self, filename: str) -> None:
        target = self.root / Path(filename).name
        if target.is_file():
            target.unlink()

    @staticmethod
    def _signature_matches(header: bytes, content_type: str) -> bool:
        if content_type == "image/jpeg":
            return header.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return header.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        if content_type in {"video/mp4", "video/quicktime"}:
            return len(header) >= 12 and header[4:8] == b"ftyp"
        if content_type == "video/webm":
            return header.startswith(b"\x1aE\xdf\xa3")
        return False
