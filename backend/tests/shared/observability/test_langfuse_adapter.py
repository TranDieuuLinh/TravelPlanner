import asyncio
from unittest.mock import MagicMock
import pytest

from app.shared.observability.langfuse_adapter import (
    LangfuseObservabilityAdapter,
    NoOpObservabilityClient,
    NoOpTrace,
)


class _V4Observation:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.updates: list[dict] = []
        self.end_count = 0

    def start_observation(self, **kwargs):
        self.started.append(kwargs)
        return _V4Observation()

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return self

    def end(self, **kwargs):
        self.end_count += 1


class _V4Client:
    def __init__(self) -> None:
        self.observations: list[_V4Observation] = []

    def start_observation(self, **kwargs):
        observation = _V4Observation()
        observation.started.append(kwargs)
        self.observations.append(observation)
        return observation

    def flush(self):
        pass

    def shutdown(self):
        pass


def test_adapter_supports_langfuse_v4_observation_api() -> None:
    client = _V4Client()
    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=client,
        capture_input_output=False,
    )

    trace = adapter.create_trace(
        trace_id="request-with-hyphens",
        name="agent.invoke",
        session_id="thread-1",
        tags=["route:explorer"],
    )
    assert not isinstance(trace, NoOpTrace)
    assert len(client.observations) == 1
    root_kwargs = client.observations[0].started[0]
    assert root_kwargs["as_type"] == "span"
    assert len(root_kwargs["trace_context"]["trace_id"]) == 32
    assert root_kwargs["metadata"]["sessionId"] == "thread-1"

    generation = trace.generation(name="gemini.generate", model="gemini")
    generation.end(usage={"input": 2, "output": 3, "total": 5})
    trace.update(tags=["status:success"])


def test_adapter_disabled_by_default_or_without_keys() -> None:
    adapter = LangfuseObservabilityAdapter(enabled=False)
    assert not adapter.is_enabled

    trace = adapter.create_trace(trace_id="t-1", name="test")
    assert isinstance(trace, NoOpTrace)
    assert trace.id == "t-1"

    span = trace.span(name="sub-span")
    gen = trace.generation(name="sub-gen")
    span.end()
    gen.end()
    asyncio.run(adapter.flush())
    asyncio.run(adapter.shutdown())


def test_adapter_with_mock_client_records_trace_and_spans() -> None:
    mock_raw_client = MagicMock()
    mock_raw_trace = MagicMock()
    mock_raw_span = MagicMock()
    mock_raw_gen = MagicMock()

    mock_raw_client.trace.return_value = mock_raw_trace
    mock_raw_trace.span.return_value = mock_raw_span
    mock_raw_trace.generation.return_value = mock_raw_gen

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host="https://cloud.langfuse.com",
        client=mock_raw_client,
    )

    assert adapter.is_enabled

    trace = adapter.create_trace(
        trace_id="req-123",
        name="agent.invoke",
        session_id="thread-456",
        tags=["env:test"],
        input_data={"prompt": "plan a trip to Hue"},
    )

    mock_raw_client.trace.assert_called_once()
    trace_kwargs = mock_raw_client.trace.call_args.kwargs
    assert trace_kwargs["id"] == "req-123"
    assert trace_kwargs["name"] == "agent.invoke"
    assert trace_kwargs["session_id"] == "thread-456"

    span = trace.span(name="place_checker.search", input={"query": "Hue"})
    mock_raw_trace.span.assert_called_once()

    gen = trace.generation(
        name="gemini.generate",
        model="gemini-2.5-flash",
        input={"prompt": "Describe Hue"},
    )
    mock_raw_trace.generation.assert_called_once()

    span.end(output={"found": True})
    mock_raw_span.end.assert_called_once()

    gen.end(
        output={"text": "Hue Citadel"},
        usage={"input": 10, "output": 20, "total": 30},
        level="DEFAULT",
    )
    mock_raw_gen.end.assert_called_once()
    gen_kwargs = mock_raw_gen.end.call_args.kwargs
    assert gen_kwargs["usage_details"] == {"input": 10, "output": 20, "total": 30}
    assert gen_kwargs["level"] == "DEFAULT"

    trace.update(output={"success": True}, tags=["status:success"])
    mock_raw_trace.update.assert_called_once()


def test_adapter_swallows_client_exceptions_gracefully() -> None:
    mock_broken_client = MagicMock()
    mock_broken_client.trace.side_effect = RuntimeError("Langfuse API unavailable")
    mock_broken_client.flush.side_effect = TimeoutError("Langfuse flush timeout")

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=mock_broken_client,
    )

    # Must not raise
    trace = adapter.create_trace(trace_id="req-fail", name="agent.invoke")
    assert isinstance(trace, NoOpTrace)

    asyncio.run(adapter.flush())
    asyncio.run(adapter.shutdown())


def test_adapter_capture_input_output_disabled_omits_previews() -> None:
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_gen = MagicMock()
    mock_client.trace.return_value = mock_trace
    mock_trace.generation.return_value = mock_gen

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        capture_input_output=False,
        client=mock_client,
    )

    trace = adapter.create_trace(
        trace_id="req-no-io",
        name="test",
        input_data={"secret_prompt": "classified info"},
    )
    trace_kwargs = mock_client.trace.call_args.kwargs
    assert trace_kwargs["input"] is None

    gen = trace.generation(name="llm", input={"prompt": "classified"})
    gen_kwargs = mock_trace.generation.call_args.kwargs
    assert gen_kwargs["input"] is None

    gen.end(output={"response": "classified result"})
    end_kwargs = mock_gen.end.call_args.kwargs
    assert "output" not in end_kwargs


def test_adapter_sampling_rate_zero_returns_noop() -> None:
    mock_client = MagicMock()
    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        sample_rate=0.0,
        client=mock_client,
    )

    trace = adapter.create_trace(trace_id="sampled-out", name="test")
    assert isinstance(trace, NoOpTrace)
    mock_client.trace.assert_not_called()
