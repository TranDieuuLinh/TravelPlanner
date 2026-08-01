from __future__ import annotations

import math

import httpx

from app.integrations.embeddings.gemini import GeminiEmbeddingClient


def test_gemini_embedding_contract_and_normalization(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={"embedding": {"values": [3.0, 4.0, 0.0]}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiEmbeddingClient(
        "secret-key",
        model="gemini-embedding-2",
        dimensions=3,
    )

    vector = client.embed_query("traditional Hanoi food")

    assert captured["url"].endswith(
        "/models/gemini-embedding-2:embedContent"
    )
    assert captured["headers"]["x-goog-api-key"] == "secret-key"
    assert captured["json"]["embedContentConfig"] == {
        "outputDimensionality": 3,
        "autoTruncate": True,
    }
    assert vector == [0.6, 0.8, 0.0]
    assert math.isclose(sum(value * value for value in vector), 1.0)
