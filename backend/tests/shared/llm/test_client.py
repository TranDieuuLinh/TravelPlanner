import asyncio

import httpx
import pytest

from app.shared.llm import (
    GeminiLlmClient,
    LlmConfigurationError,
    LlmRefusalError,
    LlmResponseError,
    LlmUnauthorizedError,
)


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


def test_client_sends_official_json_schema_generation_config() -> None:
    request_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(__import__("json").loads(request.content))
        return _response('{"value":"ok"}')

    client = GeminiLlmClient(
        "api1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    _run(client.generate("structured", response_json_schema=schema))
    config = request_body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == schema
    _run(client.aclose())


def test_client_sends_gemini_tools_at_request_root() -> None:
    request_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(__import__("json").loads(request.content))
        return _response("ok")

    client = GeminiLlmClient(
        "api1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    _run(client.generate("read this URL", tools=[{"url_context": {}}]))
    assert request_body["tools"] == [{"url_context": {}}]
    _run(client.aclose())


def test_client_does_not_retry_unauthorized_forever() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})

    client = GeminiLlmClient(
        "api1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmUnauthorizedError):
        _run(client.generate("unauthorized"))
    assert calls == 1
    _run(client.aclose())


def test_client_maps_blocked_response_to_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"promptFeedback": {"blockReason": "SAFETY"}},
        )

    client = GeminiLlmClient(
        "api1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmRefusalError):
        _run(client.generate("blocked"))
    _run(client.aclose())


def test_client_retries_server_error_only_up_to_configured_key_count() -> None:
    used_keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        used_keys.append(request.headers["x-goog-api-key"])
        if len(used_keys) == 1:
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        return _response("recovered")

    client = GeminiLlmClient(
        "api1,api2",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert _run(client.generate("retry server")) == "recovered"
    assert used_keys == ["api1", "api2"]
    _run(client.aclose())
