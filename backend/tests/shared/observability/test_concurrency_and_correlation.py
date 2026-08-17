import asyncio
from unittest.mock import MagicMock
from uuid import UUID
import httpx
import pytest

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.shared.llm import GeminiLlmClient
from app.shared.observability import (
    ObservabilityManager,
    traced_call,
)
from app.shared.observability.langfuse_adapter import LangfuseObservabilityAdapter


def test_concurrent_requests_isolate_traces_and_spans() -> None:
    mock_client = MagicMock()
    trace_a = MagicMock()
    trace_b = MagicMock()
    gen_a = MagicMock()
    gen_b = MagicMock()

    def mock_create_trace(*args, **kwargs):
        if kwargs.get("id") == "req-a":
            trace_a.id = "req-a"
            return trace_a
        trace_b.id = "req-b"
        return trace_b

    mock_client.trace.side_effect = mock_create_trace
    span_root_a = MagicMock()
    span_root_b = MagicMock()
    span_agent_a = MagicMock()
    span_agent_b = MagicMock()

    trace_a.span.return_value = span_root_a
    trace_b.span.return_value = span_root_b
    span_root_a.span.return_value = span_agent_a
    span_root_b.span.return_value = span_agent_b
    span_agent_a.generation.return_value = gen_a
    span_agent_b.generation.return_value = gen_b

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        client=mock_client,
    )
    manager = ObservabilityManager(client=adapter)

    class GraphState(TypedDict):
        prompt: str
        result: str

    async def llm_node(state: GraphState) -> dict:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": f"Answer for {state['prompt']}"}]}}
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 20,
                        "totalTokenCount": 30,
                    },
                },
            )

        client = GeminiLlmClient(
            "api1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        res = await client.generate(state["prompt"])
        await client.aclose()
        return {"result": res}

    builder = StateGraph(GraphState)
    builder.add_node("agent", llm_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    graph = builder.compile()

    async def run_request(req_id: str, prompt: str) -> None:
        cb = manager.start_trace(request_id=req_id, metadata={"threadId": f"thread-{req_id}"})
        await graph.ainvoke({"prompt": prompt, "result": ""}, config={"callbacks": [cb]})
        await manager.record_agent_invoke(
            request_id=req_id,
            route="explorer",
            success=True,
            message_length=len(prompt),
            warning_count=0,
            source_count=1,
            has_itinerary=False,
            duration_ms=50.0,
        )

    async def run_both() -> None:
        await asyncio.gather(
            run_request("req-a", "Prompt A"),
            run_request("req-b", "Prompt B"),
        )

    asyncio.run(run_both())

    # Assert span_agent_a created generation for Prompt A
    span_agent_a.generation.assert_called_once()
    assert span_agent_a.generation.call_args.kwargs["name"] == "gemini.generate"
    assert "Prompt A" in str(span_agent_a.generation.call_args.kwargs["input"])

    # Assert span_agent_b created generation for Prompt B
    span_agent_b.generation.assert_called_once()
    assert span_agent_b.generation.call_args.kwargs["name"] == "gemini.generate"
    assert "Prompt B" in str(span_agent_b.generation.call_args.kwargs["input"])

    # Assert update calls
    trace_a.update.assert_called_once()
    trace_b.update.assert_called_once()


def test_manager_record_agent_invoke_updates_tags_and_metadata() -> None:
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_client.trace.return_value = mock_trace

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        environment="test",
        client=mock_client,
    )
    manager = ObservabilityManager(client=adapter, environment="test")
    manager.start_trace(request_id="req-update-1", metadata={"route": "explorer"})

    asyncio.run(
        manager.record_agent_invoke(
            request_id="req-update-1",
            route="explorer",
            success=True,
            message_length=20,
            warning_count=1,
            source_count=3,
            has_itinerary=True,
            duration_ms=150.2,
            output={"places": 5},
        )
    )

    mock_trace.update.assert_called_once()
    update_kwargs = mock_trace.update.call_args.kwargs
    assert "status:success" in update_kwargs["tags"]
    assert "route:explorer" in update_kwargs["tags"]
    assert update_kwargs["metadata"]["durationMs"] == 150.2
    assert update_kwargs["metadata"]["hasItinerary"] is True
