from __future__ import annotations

import math
from threading import Lock
import time

import httpx


GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
)


class GeminiEmbeddingClient:
    """Small REST adapter kept behind the application's embedding interface."""

    def __init__(
        self,
        api_key: str | list[str] | tuple[str, ...],
        *,
        model: str = "gemini-embedding-2",
        dimensions: int = 768,
        timeout_seconds: float = 30.0,
        min_interval_seconds: float = 0.0,
    ) -> None:
        raw_keys = api_key.split(",") if isinstance(api_key, str) else list(api_key)
        self._api_keys = tuple(key.strip() for key in raw_keys if key.strip())
        if not self._api_keys:
            raise ValueError("At least one Gemini API key is required.")
        self._model = model
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._key_lock = Lock()
        self._next_key_index = 0
        self._request_lock = Lock()
        self._next_request_at = 0.0

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_document(self, text: str, *, title: str | None = None) -> list[float]:
        # gemini-embedding-2 uses one embedding space and does not accept taskType.
        # The title is included in the canonical document text by the caller.
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Embedding text cannot be empty.")
        payload = {
            "content": {"parts": [{"text": clean_text}]},
            "embedContentConfig": {
                "outputDimensionality": self._dimensions,
                "autoTruncate": True,
            },
        }
        last_error: Exception | None = None
        for api_key in self._keys_for_request():
            try:
                self._wait_for_request_slot()
                response = httpx.post(
                    GEMINI_EMBED_URL.format(model=self._model),
                    headers={
                        "x-goog-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                values = response.json()["embedding"]["values"]
                vector = [float(value) for value in values]
                if len(vector) != self._dimensions:
                    raise RuntimeError(
                        f"Embedding dimension mismatch: expected {self._dimensions}, "
                        f"received {len(vector)}."
                    )
                return _unit_normalize(vector)
            except (httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError) as exc:
                last_error = exc
        raise RuntimeError("Gemini embedding request failed for all configured keys.") from last_error

    def _keys_for_request(self) -> tuple[str, ...]:
        """Start each request at the next key while retaining full failover."""

        with self._key_lock:
            start = self._next_key_index
            self._next_key_index = (start + 1) % len(self._api_keys)
        return self._api_keys[start:] + self._api_keys[:start]

    def _wait_for_request_slot(self) -> None:
        if self._min_interval_seconds <= 0:
            return
        with self._request_lock:
            delay = self._next_request_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._next_request_at = time.monotonic() + self._min_interval_seconds


def _unit_normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0:
        raise RuntimeError("Embedding provider returned a zero vector.")
    return [value / magnitude for value in vector]
