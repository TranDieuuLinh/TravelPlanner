from __future__ import annotations

import asyncio
import httpx
import pytest

from app.integrations.llm.provider import GeminiLLMClient


class FakeAsyncClient:
    responses: list[httpx.Response] = []
    post_count = 0
    api_keys: list[str] = []
    payloads: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, *args, **kwargs) -> httpx.Response:
        type(self).post_count += 1
        type(self).api_keys.append(
            kwargs["headers"]["x-goog-api-key"]
        )
        type(self).payloads.append(kwargs["json"])
        return type(self).responses.pop(0)


async def _no_sleep(_: float) -> None:
    return None


def _response(status_code: int, *, text: str = "{}") -> httpx.Response:
    body = (
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": text}],
                    }
                }
            ]
        }
        if status_code < 400
        else {"error": {"code": status_code}}
    )
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", "https://example.test"),
    )


def _rate_limited_response(retry_delay: str) -> httpx.Response:
    return httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": retry_delay,
                    }
                ],
            }
        },
        request=httpx.Request("POST", "https://example.test"),
    )


def test_gemini_retries_transient_503(monkeypatch) -> None:
    FakeAsyncClient.responses = [
        _response(503),
        _response(503),
        _response(200, text='{"ok": true}'),
    ]
    FakeAsyncClient.post_count = 0
    FakeAsyncClient.api_keys = []
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(
        "app.integrations.llm.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "app.integrations.llm.provider.asyncio.sleep",
        _no_sleep,
    )

    result = asyncio.run(
        GeminiLLMClient(
            "test-key",
            "test-model",
            min_interval_seconds=0,
        ).generate_json(
            "system",
            "payload",
        )
    )

    assert result == '{"ok": true}'
    assert FakeAsyncClient.post_count == 3


def test_gemini_exhausted_503_becomes_runtime_error(monkeypatch) -> None:
    FakeAsyncClient.responses = [
        _response(503),
        _response(503),
        _response(503),
    ]
    FakeAsyncClient.post_count = 0
    FakeAsyncClient.api_keys = []
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(
        "app.integrations.llm.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "app.integrations.llm.provider.asyncio.sleep",
        _no_sleep,
    )

    with pytest.raises(
        RuntimeError,
        match="remained unavailable after 3 attempts",
    ):
        asyncio.run(
            GeminiLLMClient(
                "test-key",
                "test-model",
                min_interval_seconds=0,
            ).generate_json(
                "system",
                "payload",
            )
        )

    assert FakeAsyncClient.post_count == 3


def test_gemini_does_not_retry_authentication_error(monkeypatch) -> None:
    FakeAsyncClient.responses = [_response(401)]
    FakeAsyncClient.post_count = 0
    FakeAsyncClient.api_keys = []
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(
        "app.integrations.llm.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )

    with pytest.raises(
        RuntimeError,
        match="All configured Gemini API keys were rejected",
    ):
        asyncio.run(
            GeminiLLMClient(
                "test-key",
                "test-model",
                min_interval_seconds=0,
            ).generate_json(
                "system",
                "payload",
            )
        )

    assert FakeAsyncClient.post_count == 1


def test_gemini_rotates_to_next_key_after_quota_error(monkeypatch) -> None:
    FakeAsyncClient.responses = [
        _rate_limited_response("30s"),
        _response(200, text='{"ok": true}'),
    ]
    FakeAsyncClient.post_count = 0
    FakeAsyncClient.api_keys = []
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(
        "app.integrations.llm.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )

    result = asyncio.run(
        GeminiLLMClient(
            "key-api1,key-api2",
            "test-model",
            min_interval_seconds=0,
        ).generate_json(
            "system",
            "payload",
        )
    )

    assert result == '{"ok": true}'
    assert FakeAsyncClient.api_keys == ["key-api1", "key-api2"]


def test_gemini_passes_structured_output_schema(monkeypatch) -> None:
    FakeAsyncClient.responses = [
        _response(200, text='{"destination": "Hà Nội"}'),
    ]
    FakeAsyncClient.post_count = 0
    FakeAsyncClient.api_keys = []
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(
        "app.integrations.llm.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )
    schema = {
        "type": "object",
        "properties": {"destination": {"type": "string"}},
        "required": ["destination"],
    }

    result = asyncio.run(
        GeminiLLMClient(
            "structured-test-key",
            "test-model",
            min_interval_seconds=0,
        ).generate_structured_json(
            "system",
            "payload",
            response_schema=schema,
        )
    )

    assert result == '{"destination": "Hà Nội"}'
    assert (
        FakeAsyncClient.payloads[0]["generationConfig"][
            "responseJsonSchema"
        ]
        == schema
    )


def test_gemini_uses_provider_retry_delay() -> None:
    response = _rate_limited_response("12.5s")

    delay = GeminiLLMClient._retry_delay_seconds(response, attempt=1)

    assert delay == 12.5


def test_gemini_caps_provider_retry_delay() -> None:
    response = _rate_limited_response("120s")

    delay = GeminiLLMClient._retry_delay_seconds(response, attempt=1)

    assert delay == 60.0
