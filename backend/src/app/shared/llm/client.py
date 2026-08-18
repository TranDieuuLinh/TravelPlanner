from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import random
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
from app.shared.llm.ports import InlineMedia
from app.shared.llm.key_pool import GeminiKeyLease, GeminiKeyPool
from app.shared.observability import traced_call


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
        # Use the full configured key pool before reporting quota exhaustion.
        key_attempt_limit: int = 20,
        key_pool: GeminiKeyPool | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not model.strip():
            raise LlmConfigurationError("GEMINI_MODEL must not be empty.")
        if timeout_seconds <= 0:
            raise LlmConfigurationError("LLM timeout must be greater than zero.")
        if key_cooldown_seconds < 0:
            raise LlmConfigurationError("LLM key cooldown cannot be negative.")
        if key_attempt_limit < 1:
            raise LlmConfigurationError("LLM key attempt limit must be at least one.")

        self._key_pool = key_pool or GeminiKeyPool(
            api_key_value,
            default_cooldown_seconds=key_cooldown_seconds,
        )
        self._model = model.removeprefix("models/").strip()
        self._timeout_seconds = timeout_seconds
        self._key_cooldown_seconds = key_cooldown_seconds
        self._key_attempt_limit = key_attempt_limit
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds)
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def key_count(self) -> int:
        return self._key_pool.key_count

    @property
    def key_pool(self) -> GeminiKeyPool:
        return self._key_pool

    async def generate(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        response_json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        if not user_prompt.strip():
            raise LlmConfigurationError("LLM user prompt must not be empty.")
        payload = self._build_payload(
            user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
            tools=tools,
        )
        meta_holder: dict[str, Any] = {}
        trace_metadata = {
            "provider": "gemini",
            "model": self._model,
            "structuredOutput": response_json_schema is not None,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        async def _run() -> str:
            text, meta = await self._send_payload(payload)
            meta_holder.update(meta)
            trace_metadata.update(
                {
                    "attempts": meta.get("attempts", 1),
                    "status_code": meta.get("statusCode"),
                }
            )
            return text

        return await traced_call(
            "gemini.generate",
            _run,
            kind="llm",
            input_summary={
                "model": self._model,
                "prompt": user_prompt,
                "promptChars": len(user_prompt),
                "hasSystemPrompt": bool(system_prompt),
                "systemPrompt": system_prompt,
                "structuredOutput": response_json_schema is not None,
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "toolCount": len(tools or []),
            },
            output_summary=lambda value: {
                "responseChars": len(value),
                "response": value,
                "usage": meta_holder.get("usage"),
                "attempts": meta_holder.get("attempts", 1),
            },
            metadata=trace_metadata,
        )

    async def generate_media(
        self,
        user_prompt: str,
        media: list[InlineMedia],
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> str:
        if not user_prompt.strip() or not media:
            raise LlmConfigurationError("Multimodal requests need a prompt and media.")
        parts: list[dict[str, Any]] = [{"text": user_prompt}]
        parts.extend(
            {
                "inlineData": {
                    "mimeType": item.mime_type,
                    "data": item.data_base64,
                }
            }
            for item in media
        )
        payload = self._build_payload(
            user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
            tools=None,
            parts=parts,
        )
        meta_holder: dict[str, Any] = {}
        trace_metadata = {
            "provider": "gemini",
            "model": self._model,
            "structuredOutput": response_json_schema is not None,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        async def _run() -> str:
            text, meta = await self._send_payload(payload)
            meta_holder.update(meta)
            trace_metadata.update(
                {
                    "attempts": meta.get("attempts", 1),
                    "status_code": meta.get("statusCode"),
                }
            )
            return text

        return await traced_call(
            "gemini.generate_media",
            _run,
            kind="llm",
            input_summary={
                "model": self._model,
                "prompt": user_prompt,
                "promptChars": len(user_prompt),
                "mediaCount": len(media),
                "mediaTypes": sorted({item.mime_type for item in media}),
                "structuredOutput": response_json_schema is not None,
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
            output_summary=lambda value: {
                "responseChars": len(value),
                "response": value,
                "usage": meta_holder.get("usage"),
                "attempts": meta_holder.get("attempts", 1),
            },
            metadata=trace_metadata,
        )

    async def _send_payload(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        last_error: Exception | None = None
        attempt_limit = min(self._key_attempt_limit, self.key_count)
        attempts = 0

        for _ in range(attempt_limit):
            attempts += 1
            lease = await self._key_pool.acquire()
            try:
                response = await self._http_client.post(
                    self._endpoint,
                    headers={
                        "content-type": "application/json",
                        "x-goog-api-key": lease.value,
                    },
                    json=payload,
                )
            except httpx.TimeoutException:
                last_error = LlmTimeoutError("Gemini request timed out.")
                await self._release_with_default_cooldown(lease)
                continue
            except httpx.TransportError:
                last_error = LlmTransportError(
                    "Gemini request failed before a response was received."
                )
                await self._release_with_default_cooldown(lease)
                continue
            except BaseException:
                await self._key_pool.release(lease)
                raise

            if response.status_code >= 400:
                error = self._provider_error(response)
                if not self._should_rotate(response.status_code):
                    await self._key_pool.release(lease)
                    raise error
                last_error = error
                await self._release_failed_key(lease, response)
                continue
            await self._key_pool.release(lease)
            text, usage = self._extract_text_and_usage(response)
            return text, {
                "usage": usage,
                "attempts": attempts,
                "statusCode": response.status_code,
            }

        if last_error is not None:
            raise last_error
        raise LlmAllKeysUnavailable(self._key_cooldown_seconds)

    @property
    def _endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._model}:generateContent"
        )

    async def _release_with_default_cooldown(self, lease: GeminiKeyLease) -> None:
        await self._key_pool.release(
            lease,
            cooldown_seconds=self._with_jitter(self._key_cooldown_seconds),
        )

    async def _release_failed_key(
        self, lease: GeminiKeyLease, response: httpx.Response
    ) -> None:
        if response.status_code in {401, 403}:
            await self._key_pool.release(lease, disable=True)
            return
        retry_after = self._retry_after_seconds(response)
        cooldown = (
            retry_after
            if retry_after is not None
            else self._key_cooldown_seconds
        )
        await self._key_pool.release(
            lease,
            cooldown_seconds=self._with_jitter(cooldown),
        )

    @staticmethod
    def _with_jitter(seconds: float) -> float:
        if seconds <= 0:
            return 0
        return seconds + random.uniform(0, min(1.0, seconds * 0.1))

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, (parsed - datetime.now(UTC)).total_seconds())

    @staticmethod
    def _build_payload(
        user_prompt: str,
        *,
        system_prompt: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        response_json_schema: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None,
        parts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts or [{"text": user_prompt}]}]
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
        if tools:
            payload["tools"] = tools
        return payload

    @staticmethod
    def _should_rotate(status_code: int) -> bool:
        return status_code in {401, 403, 408, 429} or status_code >= 500

    @staticmethod
    def _provider_error(response: httpx.Response) -> LlmProviderError:
        if response.status_code in {401, 403}:
            return LlmUnauthorizedError("Gemini API key was rejected.")
        if response.status_code == 429:
            return LlmQuotaError(
                "Gemini API key quota or rate limit was reached.",
                retry_after_seconds=(
                    GeminiLlmClient._retry_after_seconds(response) or 0
                ),
            )
        if response.status_code >= 500:
            return LlmServerError("Gemini service returned a server error.")
        return LlmProviderError(
            f"Gemini request was rejected with HTTP {response.status_code}."
        )

    @staticmethod
    def _extract_text_and_usage(response: httpx.Response) -> tuple[str, dict[str, int]]:
        try:
            body = response.json()
        except ValueError as exc:
            raise LlmResponseError("Gemini returned a non-JSON response.") from exc

        usage: dict[str, int] = {}
        usage_meta = body.get("usageMetadata")
        if isinstance(usage_meta, dict):
            if isinstance(usage_meta.get("promptTokenCount"), int):
                usage["input"] = usage_meta["promptTokenCount"]
            if isinstance(usage_meta.get("candidatesTokenCount"), int):
                usage["output"] = usage_meta["candidatesTokenCount"]
            if isinstance(usage_meta.get("totalTokenCount"), int):
                usage["total"] = usage_meta["totalTokenCount"]

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
        return text, usage

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        text, _ = GeminiLlmClient._extract_text_and_usage(response)
        return text

    async def aclose(self) -> None:
        await self._http_client.aclose()
