import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.shared.llm.errors import (
    LlmAllKeysUnavailable,
    LlmConfigurationError,
    LlmProviderError,
    LlmQuotaError,
    LlmRefusalError,
    LlmResponseError,
    LlmServerError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnauthorizedError,
)


@dataclass
class _KeyState:
    value: str
    blocked_until: float = 0.0


def _parse_api_keys(api_key_value: str | None) -> list[str]:
    if not api_key_value:
        raise LlmConfigurationError(
            "GEMINI_API_KEY must contain at least one comma-separated API key."
        )
    keys: list[str] = []
    seen: set[str] = set()
    for raw_key in api_key_value.split(","):
        key = raw_key.strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    if not keys:
        raise LlmConfigurationError(
            "GEMINI_API_KEY must contain at least one comma-separated API key."
        )
    return keys


class GeminiLlmClient:
    """Small shared Gemini client with round-robin key rotation.

    The client uses Gemini's REST ``generateContent`` endpoint so feature
    modules do not depend on a provider SDK. Keys that receive quota,
    authorization, transport, or server errors are cooled down and skipped
    for subsequent attempts.
    """

    def __init__(
        self,
        api_key_value: str | None,
        *,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 30.0,
        key_cooldown_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not model.strip():
            raise LlmConfigurationError("GEMINI_MODEL must not be empty.")
        if timeout_seconds <= 0:
            raise LlmConfigurationError("LLM timeout must be greater than zero.")
        if key_cooldown_seconds < 0:
            raise LlmConfigurationError("LLM key cooldown cannot be negative.")

        self._keys = [_KeyState(value=key) for key in _parse_api_keys(api_key_value)]
        self._model = model.removeprefix("models/").strip()
        self._timeout_seconds = timeout_seconds
        self._key_cooldown_seconds = key_cooldown_seconds
        self._next_key_index = 0
        self._key_lock = asyncio.Lock()
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds)
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def key_count(self) -> int:
        return len(self._keys)

    async def generate(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> str:
        if not user_prompt.strip():
            raise LlmConfigurationError("LLM user prompt must not be empty.")
        payload = self._build_payload(
            user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
        )
        last_error: Exception | None = None

        for _ in range(len(self._keys)):
            key_index, api_key = await self._next_available_key()
            try:
                response = await self._http_client.post(
                    self._endpoint,
                    headers={
                        "content-type": "application/json",
                        "x-goog-api-key": api_key,
                    },
                    json=payload,
                )
            except httpx.TimeoutException:
                last_error = LlmTimeoutError("Gemini request timed out.")
                await self._cool_down(key_index)
                continue
            except httpx.TransportError:
                last_error = LlmTransportError(
                    "Gemini request failed before a response was received."
                )
                await self._cool_down(key_index)
                continue

            if response.status_code >= 400:
                error = self._provider_error(response)
                if not self._should_rotate(response.status_code):
                    raise error
                last_error = error
                await self._cool_down(key_index)
                continue
            return self._extract_text(response)

        if last_error is not None:
            raise last_error
        raise LlmAllKeysUnavailable(self._key_cooldown_seconds)

    @property
    def _endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._model}:generateContent"
        )

    async def _next_available_key(self) -> tuple[int, str]:
        async with self._key_lock:
            now = time.monotonic()
            for offset in range(len(self._keys)):
                index = (self._next_key_index + offset) % len(self._keys)
                state = self._keys[index]
                if state.blocked_until <= now:
                    self._next_key_index = (index + 1) % len(self._keys)
                    return index, state.value
            retry_after = min(
                state.blocked_until - now
                for state in self._keys
                if state.blocked_until > now
            )
        raise LlmAllKeysUnavailable(max(0.0, retry_after))

    async def _cool_down(self, key_index: int) -> None:
        async with self._key_lock:
            self._keys[key_index].blocked_until = (
                time.monotonic() + self._key_cooldown_seconds
            )

    @staticmethod
    def _build_payload(
        user_prompt: str,
        *,
        system_prompt: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        response_json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}]
        }
        if system_prompt and system_prompt.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = max_output_tokens
        if response_json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseJsonSchema"] = response_json_schema
        if generation_config:
            payload["generationConfig"] = generation_config
        return payload

    @staticmethod
    def _should_rotate(status_code: int) -> bool:
        return status_code in {401, 403, 408, 429} or status_code >= 500

    @staticmethod
    def _provider_error(response: httpx.Response) -> LlmProviderError:
        if response.status_code in {401, 403}:
            return LlmUnauthorizedError("Gemini API key was rejected.")
        if response.status_code == 429:
            return LlmQuotaError("Gemini API key quota or rate limit was reached.")
        if response.status_code >= 500:
            return LlmServerError("Gemini service returned a server error.")
        return LlmProviderError(
            f"Gemini request was rejected with HTTP {response.status_code}."
        )

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError as exc:
            raise LlmResponseError("Gemini returned a non-JSON response.") from exc

        candidates = body.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            if body.get("promptFeedback", {}).get("blockReason"):
                raise LlmRefusalError("Gemini refused the prompt.")
            raise LlmResponseError("Gemini returned no candidate response.")
        finish_reason = candidates[0].get("finishReason")
        if finish_reason in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}:
            raise LlmRefusalError("Gemini refused to generate an answer.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
        if not text:
            raise LlmResponseError("Gemini returned no text content.")
        return text

    async def aclose(self) -> None:
        await self._http_client.aclose()
