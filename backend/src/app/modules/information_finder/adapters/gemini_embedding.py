import math
import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.modules.information_finder.contract import EmbeddingIdentity
from app.modules.information_finder.errors import (
    EmbeddingProviderError,
    EmbeddingProviderInvalidOutput,
    EmbeddingProviderQuotaExceeded,
    EmbeddingProviderTimeout,
    EmbeddingProviderUnauthorized,
)


@dataclass
class _KeyState:
    value: str
    blocked_until: float = 0.0


def _parse_api_keys(value: str | None) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for raw_key in (value or "").split(","):
        key = raw_key.strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    if not keys:
        raise EmbeddingProviderError(
            "GEMINI_API_KEY must contain at least one comma-separated API key"
        )
    return keys


class GeminiEmbeddingProvider:
    """Gemini retrieval embeddings backed by the REST Embed Content API."""

    _base_url = "https://generativelanguage.googleapis.com/v1beta"
    _max_batch_size = 100

    def __init__(
        self,
        api_key: str | None,
        *,
        model_name: str = "gemini-embedding-001",
        model_revision: str | None = None,
        dimensions: int = 384,
        timeout_seconds: float = 30.0,
        key_cooldown_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if dimensions < 1:
            raise ValueError("Embedding dimensions must be positive")
        if timeout_seconds <= 0:
            raise ValueError("Embedding timeout must be greater than zero")
        if key_cooldown_seconds < 0:
            raise ValueError("Embedding key cooldown cannot be negative")
        self._keys = [_KeyState(value=key) for key in _parse_api_keys(api_key)]
        self._key_cooldown_seconds = key_cooldown_seconds
        self._next_key_index = 0
        self._key_lock = asyncio.Lock()
        self._model_path = (
            model_name if model_name.startswith("models/") else f"models/{model_name}"
        )
        self._identity = EmbeddingIdentity(
            model_name=model_name.removeprefix("models/"),
            model_revision=model_revision,
            dimensions=dimensions,
        )
        self._timeout = timeout_seconds
        self._client = client

    @property
    def key_count(self) -> int:
        return len(self._keys)

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed_one(text, "RETRIEVAL_QUERY")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            payload = {
                "requests": [
                    self._request(text, "RETRIEVAL_DOCUMENT") for text in batch
                ]
            }
            data = await self._post(":batchEmbedContents", payload)
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise EmbeddingProviderInvalidOutput(
                    "Gemini returned an invalid embedding batch"
                )
            vectors.extend(self._vector(item) for item in embeddings)
        return vectors

    async def _embed_one(self, text: str, task_type: str) -> list[float]:
        data = await self._post(":embedContent", self._request(text, task_type))
        return self._vector(data.get("embedding"))

    def _request(self, text: str, task_type: str) -> dict[str, Any]:
        # The v1beta REST endpoint currently honors these compatibility fields
        # at the request root. Sending the same values only inside
        # embedContentConfig returns the model's full 3072-dimensional vector,
        # which violates the module's persisted 384-dimensional identity.
        return {
            "model": self._model_path,
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self.identity.dimensions,
        }

    async def _post(self, operation: str, payload: dict[str, Any]) -> Mapping[str, Any]:
        url = f"{self._base_url}/{self._model_path}{operation}"
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        last_error: EmbeddingProviderError | None = None
        try:
            for _ in range(len(self._keys)):
                key_index, api_key = await self._next_available_key()
                try:
                    response = await client.post(
                        url,
                        headers={"x-goog-api-key": api_key},
                        json=payload,
                    )
                except httpx.TimeoutException:
                    last_error = EmbeddingProviderTimeout(
                        "Gemini embedding request timed out"
                    )
                    await self._cool_down(key_index)
                    continue
                except httpx.RequestError:
                    last_error = EmbeddingProviderError(
                        "Gemini embedding request failed"
                    )
                    await self._cool_down(key_index)
                    continue

                if response.status_code in (401, 403):
                    last_error = EmbeddingProviderUnauthorized(
                        "Gemini embedding authorization failed"
                    )
                elif response.status_code == 429:
                    last_error = EmbeddingProviderQuotaExceeded(
                        "Gemini embedding quota or rate limit reached"
                    )
                elif response.status_code == 408 or response.status_code >= 500:
                    last_error = EmbeddingProviderError(
                        self._http_error_message(response)
                    )
                elif response.is_error:
                    raise EmbeddingProviderError(self._http_error_message(response))
                else:
                    return self._parse_response(response)
                await self._cool_down(key_index)
        finally:
            if own_client:
                await client.aclose()

        if last_error is not None:
            raise last_error
        raise EmbeddingProviderError("No Gemini embedding key was available")

    @staticmethod
    def _parse_response(response: httpx.Response) -> Mapping[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise EmbeddingProviderInvalidOutput(
                "Gemini embedding response was not valid JSON"
            ) from exc
        if not isinstance(data, Mapping):
            raise EmbeddingProviderInvalidOutput(
                "Gemini embedding response was not an object"
            )
        return data

    @staticmethod
    def _http_error_message(response: httpx.Response) -> str:
        message = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, Mapping):
            error = payload.get("error")
            if isinstance(error, Mapping) and isinstance(error.get("message"), str):
                message = " ".join(error["message"].split())[:300]
        suffix = f": {message}" if message else ""
        return (
            f"Gemini embedding provider returned HTTP {response.status_code}"
            f"{suffix}"
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
        raise EmbeddingProviderError("All Gemini embedding keys are cooling down")

    async def _cool_down(self, key_index: int) -> None:
        async with self._key_lock:
            self._keys[key_index].blocked_until = (
                time.monotonic() + self._key_cooldown_seconds
            )

    def _vector(self, value: Any) -> list[float]:
        if not isinstance(value, Mapping) or not isinstance(value.get("values"), list):
            raise EmbeddingProviderInvalidOutput(
                "Gemini response did not contain embedding values"
            )
        values = value["values"]
        if len(values) != self.identity.dimensions or not all(
            isinstance(item, (int, float)) and math.isfinite(float(item))
            for item in values
        ):
            raise EmbeddingProviderInvalidOutput(
                "Gemini returned unexpected embedding dimensions"
            )
        norm = math.sqrt(sum(float(item) ** 2 for item in values))
        if norm == 0:
            raise EmbeddingProviderInvalidOutput("Gemini returned a zero embedding")
        return [float(item) / norm for item in values]
