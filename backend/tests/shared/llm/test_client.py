import asyncio

import httpx
import pytest

from app.shared.llm import GeminiLlmClient, LlmConfigurationError, LlmResponseError


def _run(coro):
    return asyncio.run(coro)


def _response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
    )


def test_client_parses_one_comma_separated_key_value() -> None:
    client = GeminiLlmClient(" api1,api2,api1,, ")

    assert client.key_count == 2

    _run(client.aclose())


def test_client_rotates_keys_round_robin() -> None:
    used_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        used_keys.append(request.headers["x-goog-api-key"])
        return _response("ok")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient("api1,api2,api3", http_client=http_client)

    assert _run(client.generate("first")) == "ok"
    assert _run(client.generate("second")) == "ok"
    assert _run(client.generate("third")) == "ok"
    assert used_keys == ["api1", "api2", "api3"]

    _run(client.aclose())


def test_client_rotates_after_quota_response() -> None:
    used_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["x-goog-api-key"]
        used_keys.append(key)
        if key == "api1":
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
        return _response("recovered")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient(
        "api1,api2",
        key_cooldown_seconds=60,
        http_client=http_client,
    )

    assert _run(client.generate("retry")) == "recovered"
    assert used_keys == ["api1", "api2"]

    _run(client.aclose())


def test_client_rejects_empty_configuration() -> None:
    with pytest.raises(LlmConfigurationError):
        GeminiLlmClient(" , ")


def test_client_rejects_response_without_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient("api1", http_client=http_client)

    with pytest.raises(LlmResponseError):
        _run(client.generate("missing text"))

    _run(client.aclose())
