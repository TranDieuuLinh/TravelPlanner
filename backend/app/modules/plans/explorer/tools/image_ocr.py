from __future__ import annotations

from app.core.config import settings
from app.integrations.llm.base import LLMClient, LLMImageInput
from app.modules.plans.explorer.schema import ExploreImageContext

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class ImageOcrService:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def extract_many(
        self,
        images: list["ImageUploadPayload"],
        *,
        destination: str | None,
    ) -> list[ExploreImageContext]:
        contexts: list[ExploreImageContext] = []
        try:
            for image in images:
                try:
                    contexts.append(
                        await self.extract(
                            file_name=image.file_name,
                            mime_type=image.mime_type,
                            data=image.data,
                            destination=destination,
                        )
                    )
                finally:
                    image.clear_data()
        finally:
            for image in images:
                image.clear_data()
        return contexts

    async def extract(
        self,
        *,
        file_name: str,
        mime_type: str | None,
        data: bytes,
        destination: str | None,
    ) -> ExploreImageContext:
        detected_mime_type = mime_type or "application/octet-stream"
        if detected_mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            return ExploreImageContext(
                fileName=file_name,
                mimeType=detected_mime_type,
                status="unsupported",
                error="Only JPEG, PNG, WebP, HEIC, and HEIF images are supported.",
            )
        if not data:
            return ExploreImageContext(
                fileName=file_name,
                mimeType=detected_mime_type,
                status="failed",
                error="Uploaded image was empty.",
            )

        system_prompt = (
            "You are an OCR extractor for travel planning screenshots and images. "
            "Return concise plain text only. Transcribe visible text, place names, addresses, prices, dates, notes, captions, and travel-relevant labels. "
            "If the image has no readable travel information, say so briefly. Do not invent missing text."
        )
        user_text = "Extract travel-relevant OCR text from this uploaded image."
        if destination:
            user_text += f" The user's destination context is {destination}."

        try:
            ocr_text = await self.llm.generate_text_from_images(
                system_prompt=system_prompt,
                user_text=user_text,
                images=[LLMImageInput(data=data, mime_type=detected_mime_type)],
                model=settings.gemini_image_ocr_model,
            )
        except Exception as exc:
            return ExploreImageContext(
                fileName=file_name,
                mimeType=detected_mime_type,
                status="failed",
                error=str(exc),
            )

        return ExploreImageContext(
            fileName=file_name,
            mimeType=detected_mime_type,
            ocrText=ocr_text.strip(),
            status="ok",
        )


class ImageUploadPayload:
    def __init__(self, *, file_name: str, mime_type: str | None, data: bytes) -> None:
        self.file_name = file_name
        self.mime_type = mime_type
        self.data = data

    def clear_data(self) -> None:
        self.data = b""
