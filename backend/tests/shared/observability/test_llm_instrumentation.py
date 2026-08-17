import asyncio
from unittest.mock import MagicMock
import httpx
import pytest

from app.shared.llm import GeminiLlmClient, InlineMedia, LlmQuotaError
from app.shared.observability import (
    ObservabilityManager,
    TraceCallbackHandler,
    set_current_trace_callback,
)
from app.shared.observability.langfuse_adapter import LangfuseObservabilityAdapter


def _run(coro):
    return asyncio.run(coro)


def test_gemini_client_generation_captures_tokens_and_metadata() -> None:
    mock_lf_client = MagicMock()
    mock_lf_trace = MagicMock()
    mock_lf_gen = MagicMock()
    mock_lf_client.trace.return_value = mock_lf_trace
    mock_lf_trace.generation.return_value = mock_lf_gen

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=mock_lf_client,
    )
    manager = ObservabilityManager(client=adapter)
    callback = manager.start_trace(
        request_id="req-llm-1",
        metadata={"threadId": "thread-1"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Hello from Gemini"}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 15,
                    "candidatesTokenCount": 25,
                    "totalTokenCount": 40,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient(
        "api1",
        model="gemini-2.5-flash",
        http_client=http_client,
    )

    result = _run(client.generate("What is Hue?"))
    assert result == "Hello from Gemini"

    # Verify Langfuse generation creation and end
    mock_lf_trace.generation.assert_called_once()
    gen_kwargs = mock_lf_trace.generation.call_args.kwargs
    assert gen_kwargs["name"] == "gemini.generate"
    assert gen_kwargs["model"] == "gemini-2.5-flash"

    mock_lf_gen.end.assert_called_once()
    end_kwargs = mock_lf_gen.end.call_args.kwargs
    assert end_kwargs["usage_details"] == {
        "input": 15,
        "output": 25,
        "total": 40,
    }
    assert end_kwargs["level"] == "DEFAULT"

    _run(client.aclose())


def test_gemini_client_generation_failure_captures_error_level() -> None:
    mock_lf_client = MagicMock()
    mock_lf_trace = MagicMock()
    mock_lf_gen = MagicMock()
    mock_lf_client.trace.return_value = mock_lf_trace
    mock_lf_trace.generation.return_value = mock_lf_gen

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=mock_lf_client,
    )
    manager = ObservabilityManager(client=adapter)
    callback = manager.start_trace(request_id="req-llm-fail")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"status": "RESOURCE_EXHAUSTED"}},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient(
        "api1",
        key_attempt_limit=1,
        http_client=http_client,
    )

    with pytest.raises(LlmQuotaError):
        _run(client.generate("This will hit 429"))

    mock_lf_gen.end.assert_called_once()
    end_kwargs = mock_lf_gen.end.call_args.kwargs
    assert end_kwargs["level"] == "ERROR"
    assert "Gemini API key quota" in end_kwargs["status_message"]

    _run(client.aclose())


def test_gemini_client_generate_media_captures_multimodal_metadata() -> None:
    mock_lf_client = MagicMock()
    mock_lf_trace = MagicMock()
    mock_lf_gen = MagicMock()
    mock_lf_client.trace.return_value = mock_lf_trace
    mock_lf_trace.generation.return_value = mock_lf_gen

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=mock_lf_client,
    )
    manager = ObservabilityManager(client=adapter)
    callback = manager.start_trace(request_id="req-media-1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Found citadel in image"}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 50,
                    "totalTokenCount": 150,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GeminiLlmClient(
        "api1",
        model="gemini-2.5-flash",
        http_client=http_client,
    )

    result = _run(
        client.generate_media(
            "Extract OCR",
            [InlineMedia(mime_type="image/jpeg", data_base64="YWJj")],
        )
    )
    assert result == "Found citadel in image"

    mock_lf_trace.generation.assert_called_once()
    gen_kwargs = mock_lf_trace.generation.call_args.kwargs
    assert gen_kwargs["name"] == "gemini.generate_media"

    mock_lf_gen.end.assert_called_once()
    end_kwargs = mock_lf_gen.end.call_args.kwargs
    assert end_kwargs["usage_details"] == {
        "input": 100,
        "output": 50,
        "total": 150,
    }

    _run(client.aclose())
