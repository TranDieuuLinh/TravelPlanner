from __future__ import annotations

import math

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
    ) -> None:
        raw_keys = api_key.split(",") if isinstance(api_key, str) else list(api_key)
        self._api_keys = tuple(key.strip() for key in raw_keys if key.strip())
        if not self._api_keys:
            raise ValueError("At least one Gemini API key is required.")
        self._model = model
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds

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
        for api_key in self._api_keys:
            try:
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


def _unit_normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0:
        raise RuntimeError("Embedding provider returned a zero vector.")
    return [value / magnitude for value in vector]
