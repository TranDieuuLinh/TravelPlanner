import asyncio
import base64
import json
import re
import time

import httpx

from app.core.config import settings
from app.integrations.llm.base import (
    GroundedStructuredResult,
    GroundingSource,
    LLMClient,
    LLMImageInput,
)

GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MAX_ATTEMPTS = 3
GEMINI_MAX_RETRY_DELAY_SECONDS = 60.0
GEMINI_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class _GeminiRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_call_started_at = 0.0
        self._next_call_not_before = 0.0

    async def wait(self, min_interval_seconds: float) -> None:
        async with self._lock:
            now = time.monotonic()
            min_interval_target = (
                self._last_call_started_at + min_interval_seconds
            )
            target = max(
                min_interval_target,
                self._next_call_not_before,
            )
            remaining = target - now
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_call_started_at = time.monotonic()

    async def defer(self, seconds: float) -> None:
        async with self._lock:
            self._next_call_not_before = max(
                self._next_call_not_before,
                time.monotonic() + seconds,
            )


_gemini_rate_limiter = _GeminiRateLimiter()


class StubLLMClient(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        return f"Draft travel profile generated from: {prompt}"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raise RuntimeError("No LLM provider configured.")

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        """Return a safe local supervisor response when no provider is set.

        The deterministic routing in ConversationSupervisor handles the common
        high-signal cases before reaching here. This fallback exists for the
        remaining ambiguous cases so local development gets a useful question
        instead of a provider error. It intentionally never proposes a plan
        mutation and never claims that an action was completed.
        """
        del system_prompt, response_schema
        try:
            payload = json.loads(user_payload)
        except (TypeError, ValueError):
            payload = {}
        current_plan = payload.get("currentPlan")
        if current_plan:
            response = {
                "intent": "clarify",
                "confidence": 0.9,
                "responseText": "Mình cần biết rõ bạn muốn tư vấn hay thay đổi mục nào trong lịch trình.",
                "clarifyingQuestion": "Bạn muốn xem giải thích, thêm địa điểm, hay chỉnh sửa một điểm cụ thể?",
                "options": [
                    {"label": "Tư vấn", "value": "Tư vấn về lịch trình hiện tại"},
                    {"label": "Thêm địa điểm", "value": "Thêm một địa điểm vào lịch trình"},
                    {"label": "Chỉnh sửa", "value": "Chỉnh sửa một địa điểm trong lịch trình"},
                ],
            }
        else:
            response = {
                "intent": "travel_advice",
                "confidence": 0.85,
                "responseText": "Mình có thể tư vấn điểm đến hoặc hỗ trợ bạn lên lịch trình. Bạn muốn hỏi điều gì?",
            }
        return json.dumps(response, ensure_ascii=False)


class GeminiLLMClient(LLMClient):
    def __init__(
        self,
        api_key: str | list[str] | tuple[str, ...],
        model: str | None = None,
        *,
        min_interval_seconds: float = 0.0,
    ) -> None:
        raw_keys = (
            api_key.split(",")
            if isinstance(api_key, str)
            else list(api_key)
        )
        self._api_keys = tuple(
            key.strip()
            for key in raw_keys
            if key.strip()
        )
        if not self._api_keys:
            raise ValueError("At least one Gemini API key is required.")
        self.model = model or settings.gemini_model
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._key_lock = asyncio.Lock()
        self._current_key_index = 0
        self._key_cooldown_until: dict[int, float] = {}
        self._disabled_key_indexes: set[int] = set()

    async def generate_profile_plan(self, prompt: str) -> str:
        return await self.generate_json(
            system_prompt="Return a concise travel planning draft as plain JSON.",
            user_payload=prompt,
        )

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        return await self.generate_structured_json(
            system_prompt,
            user_payload,
            response_schema={},
        )

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        generation_config = {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        }
        if response_schema:
            generation_config["responseJsonSchema"] = response_schema
        data = await self._generate_content(
            model=self.model,
            payload={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [
                    {"role": "user", "parts": [{"text": user_payload}]}
                ],
                "generationConfig": generation_config,
            },
        )
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
        data = await self._generate_content(
            model=model or self.model,
            payload={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "temperature": 0.0,
                    "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                },
            },
        )
        return self._extract_text(data)

    async def generate_grounded_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> GroundedStructuredResult:
        """Return schema-bound JSON grounded by Google Search.

        The raw search payload is deliberately not exposed to domain code. Only
        the model JSON, public source title/URI pairs and search-query strings
        cross the provider boundary.
        """
        generation_config: dict = {
            "responseMimeType": "application/json",
            "temperature": 0.0,
        }
        if response_schema:
            generation_config["responseJsonSchema"] = response_schema
        data = await self._generate_content(
            model=self.model,
            payload={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [
                    {"role": "user", "parts": [{"text": user_payload}]}
                ],
                "tools": [{"google_search": {}}],
                "generationConfig": generation_config,
            },
        )
        candidate = (data.get("candidates") or [{}])[0]
        grounding = candidate.get("groundingMetadata") or {}
        sources: list[GroundingSource] = []
        seen_uris: set[str] = set()
        for chunk in grounding.get("groundingChunks") or []:
            web = chunk.get("web") if isinstance(chunk, dict) else None
            if not isinstance(web, dict):
                continue
            uri = str(web.get("uri") or "").strip()
            if not uri or uri in seen_uris:
                continue
            seen_uris.add(uri)
            sources.append(
                GroundingSource(
                    title=str(web.get("title") or uri).strip()[:500],
                    uri=uri[:2048],
                )
            )
        queries = tuple(
            str(query).strip()[:500]
            for query in grounding.get("webSearchQueries") or []
            if str(query).strip()
        )
        return GroundedStructuredResult(
            text=self._extract_text(data),
            sources=tuple(sources),
            search_queries=queries,
        )

    async def _generate_content(
        self,
        *,
        model: str,
        payload: dict,
    ) -> dict:
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model)
        max_attempts = max(
            GEMINI_MAX_ATTEMPTS,
            len(self._api_keys) * 2 + 1,
        )
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(1, max_attempts + 1):
                key_index, api_key = await self._acquire_api_key()
                await _gemini_rate_limiter.wait(
                    self.min_interval_seconds
                )
                try:
                    response = await client.post(
                        url,
                        headers={
                            "x-goog-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                except httpx.RequestError as exc:
                    if attempt == max_attempts:
                        raise RuntimeError(
                            "Gemini request failed after retrying a network error."
                        ) from exc
                    await _gemini_rate_limiter.defer(
                        1.0 * (2 ** (attempt - 1))
                    )
                    continue

                if response.status_code == 429:
                    await self._mark_key_quota_exhausted(
                        key_index,
                        self._retry_delay_seconds(response, attempt),
                    )
                    if attempt == max_attempts:
                        raise RuntimeError(
                            "All configured Gemini API keys remained quota "
                            "limited after retrying."
                        )
                    continue

                if response.status_code in GEMINI_RETRYABLE_STATUS_CODES:
                    if attempt == max_attempts:
                        raise RuntimeError(
                            "Gemini request remained unavailable after "
                            f"{max_attempts} attempts "
                            f"(status {response.status_code})."
                        )
                    await _gemini_rate_limiter.defer(
                        self._retry_delay_seconds(response, attempt)
                    )
                    continue

                if response.status_code in {401, 403}:
                    await self._disable_key(key_index)
                    if attempt == max_attempts:
                        raise RuntimeError(
                            "All configured Gemini API keys were rejected."
                        )
                    continue

                if response.is_error:
                    raise RuntimeError(
                        "Gemini request was rejected "
                        f"(status {response.status_code})."
                    )

                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        "Gemini returned a non-JSON response."
                    ) from exc

        raise RuntimeError("Gemini request failed unexpectedly.")

    async def _acquire_api_key(self) -> tuple[int, str]:
        while True:
            async with self._key_lock:
                now = time.monotonic()
                available_indexes = [
                    index
                    for index in range(len(self._api_keys))
                    if index not in self._disabled_key_indexes
                ]
                if not available_indexes:
                    raise RuntimeError(
                        "All configured Gemini API keys were rejected."
                    )

                for offset in range(len(self._api_keys)):
                    index = (
                        self._current_key_index + offset
                    ) % len(self._api_keys)
                    if index not in available_indexes:
                        continue
                    if self._key_cooldown_until.get(index, 0.0) <= now:
                        self._current_key_index = (
                            index + 1
                        ) % len(self._api_keys)
                        return index, self._api_keys[index]

                earliest_ready = min(
                    self._key_cooldown_until.get(index, now)
                    for index in available_indexes
                )
                wait_seconds = max(0.0, earliest_ready - now)

            await asyncio.sleep(wait_seconds)

    async def _mark_key_quota_exhausted(
        self,
        key_index: int,
        retry_delay_seconds: float,
    ) -> None:
        async with self._key_lock:
            self._key_cooldown_until[key_index] = max(
                self._key_cooldown_until.get(key_index, 0.0),
                time.monotonic() + retry_delay_seconds,
            )
            self._current_key_index = (
                key_index + 1
            ) % len(self._api_keys)

    async def _disable_key(self, key_index: int) -> None:
        async with self._key_lock:
            self._disabled_key_indexes.add(key_index)
            self._current_key_index = (
                key_index + 1
            ) % len(self._api_keys)

    @staticmethod
    def _retry_delay_seconds(
        response: httpx.Response,
        attempt: int,
    ) -> float:
        candidates: list[float] = []
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                candidates.append(float(retry_after))
            except ValueError:
                pass

        try:
            details = response.json().get("error", {}).get("details", [])
        except ValueError:
            details = []
        for detail in details:
            retry_delay = detail.get("retryDelay")
            if not isinstance(retry_delay, str):
                continue
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", retry_delay.strip())
            if match:
                candidates.append(float(match.group(1)))

        fallback = 1.0 * (2 ** (attempt - 1))
        requested = max(candidates, default=fallback)
        return min(
            max(1.0, requested),
            GEMINI_MAX_RETRY_DELAY_SECONDS,
        )

    def _extract_text(self, data: dict) -> str:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts if part.get("text"))
        if not text:
            raise RuntimeError("Gemini response did not include text content.")
        return text
