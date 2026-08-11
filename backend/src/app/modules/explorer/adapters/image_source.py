import base64
import binascii
from datetime import UTC, datetime

from app.modules.explorer.contract import ExplorerImageInput
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult
from app.modules.explorer.ports import MediaAnalyzer


class GeminiImageSourceExtractor:
    def __init__(self, analyzer: MediaAnalyzer) -> None:
        self.analyzer = analyzer

    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult:
        if image.ocr_text:
            text = image.ocr_text.strip()
        else:
            try:
                base64.b64decode(image.data_base64 or "", validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ExplorerOperationError(
                    "IMAGE_BASE64_INVALID", "Dữ liệu ảnh base64 không hợp lệ."
                ) from exc
            try:
                text = await self.analyzer.analyze_image(
                    image.data_base64 or "", image.mime_type
                )
            except Exception as exc:
                if isinstance(exc, ExplorerOperationError):
                    raise
                raise ExplorerOperationError(
                    "IMAGE_OCR_FAILED", "Gemini không OCR được ảnh.", retryable=True
                ) from exc
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
