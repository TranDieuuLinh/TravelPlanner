from __future__ import annotations

import asyncio

from app.integrations.llm.base import LLMClient, LLMImageInput
from app.modules.plans.explorer.tools.image_ocr import (
    ImageOcrService,
    ImageUploadPayload,
)


class FakeImageLlm(LLMClient):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.received_image = False

    async def generate_profile_plan(self, prompt: str) -> str:
        return "unused"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        return "{}"

    async def generate_text_from_images(
        self,
        system_prompt: str,
        user_text: str,
        images: list[LLMImageInput],
        *,
        model: str | None = None,
    ) -> str:
        self.received_image = images[0].data == b"image-content"
        if self.fail:
            raise RuntimeError("OCR failed")
        return "Hoan Kiem Lake"


def test_clears_image_bytes_after_successful_ocr() -> None:
    llm = FakeImageLlm()
    payload = ImageUploadPayload(
        file_name="place.png",
        mime_type="image/png",
        data=b"image-content",
    )

    contexts = asyncio.run(
        ImageOcrService(llm).extract_many([payload], destination="Hanoi")
    )

    assert llm.received_image is True
    assert contexts[0].ocr_text == "Hoan Kiem Lake"
    assert payload.data == b""


def test_clears_image_bytes_when_ocr_fails() -> None:
    payload = ImageUploadPayload(
        file_name="place.png",
        mime_type="image/png",
        data=b"image-content",
    )

    contexts = asyncio.run(
        ImageOcrService(FakeImageLlm(fail=True)).extract_many(
            [payload],
            destination="Hanoi",
        )
    )

    assert contexts[0].status == "failed"
    assert payload.data == b""
