import base64

import httpx

from app.core.config import settings
from app.integrations.llm.base import LLMClient, LLMImageInput

GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class StubLLMClient(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        return f"Draft travel profile generated from: {prompt}"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raise RuntimeError("No LLM provider configured.")


class GeminiLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or settings.gemini_model

    async def generate_profile_plan(self, prompt: str) -> str:
        return await self.generate_json(
            system_prompt="Return a concise travel planning draft as plain JSON.",
            user_payload=prompt,
        )

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                GEMINI_GENERATE_CONTENT_URL.format(model=self.model),
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.1,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        return self._extract_text(data)

    async def generate_text_from_images(
        self,
        system_prompt: str,
        user_text: str,
        images: list[LLMImageInput],
        *,
        model: str | None = None,
    ) -> str:
        parts = [{"text": user_text}]
        parts.extend(
            {
                "inline_data": {
                    "mime_type": image.mime_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                }
            }
            for image in images
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                GEMINI_GENERATE_CONTENT_URL.format(model=model or self.model),
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        return self._extract_text(data)

    def _extract_text(self, data: dict) -> str:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts if part.get("text"))
        if not text:
            raise RuntimeError("Gemini response did not include text content.")
        return text
