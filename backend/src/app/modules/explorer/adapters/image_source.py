import base64
import binascii
from datetime import UTC, datetime
import hashlib

from app.modules.explorer.contract import ExplorerImageInput
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult
from app.modules.explorer.ports import ImageOcrCache, MediaAnalyzer


class GeminiImageSourceExtractor:
    def __init__(
        self,
        analyzer: MediaAnalyzer,
        cache: ImageOcrCache | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.cache = cache

    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
        force_refresh: bool = False,
    ) -> SourceExtractionResult:
        if image.ocr_text:
            text = image.ocr_text.strip()
        else:
            try:
                image_bytes = base64.b64decode(
                    image.data_base64 or "", validate=True
                )
            except (ValueError, binascii.Error) as exc:
                raise ExplorerOperationError(
                    "IMAGE_BASE64_INVALID", "Dữ liệu ảnh base64 không hợp lệ."
                ) from exc
            cache_key = self._cache_key(image_bytes, image.mime_type)
            text = None
            if self.cache is not None and not force_refresh:
                text = await self.cache.get(cache_key)
            if text is None:
                try:
                    text = await self.analyzer.analyze_image(
                        image.data_base64 or "", image.mime_type
                    )
                except Exception as exc:
                    if isinstance(exc, ExplorerOperationError):
                        raise
                    raise ExplorerOperationError(
                        "IMAGE_OCR_FAILED",
                        "Gemini không OCR được ảnh.",
                        retryable=True,
                    ) from exc
                if self.cache is not None and text:
                    await self.cache.save(cache_key, text)
        if not text:
            raise ExplorerOperationError("IMAGE_OCR_EMPTY", "Ảnh không có text hữu ích.")
        artifact = SourceArtifact(
            artifactType="image_ocr",
            text=text[:60_000],
            observedAt=datetime.now(UTC).isoformat(),
        )
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="image",
            sourceRef=image.file_name,
            status="succeeded",
            artifacts=[artifact],
        )

    @staticmethod
    def _cache_key(image_bytes: bytes, mime_type: str) -> str:
        digest = hashlib.sha256()
        digest.update(mime_type.casefold().strip().encode())
        digest.update(b"\0")
        digest.update(image_bytes)
        return digest.hexdigest()
