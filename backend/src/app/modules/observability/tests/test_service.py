import asyncio
import logging
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.service import ObservabilityService
from app.shared.observability import traced_call


def test_local_store_captures_redacted_tool_input_and_output(tmp_path) -> None:
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    callback = service.start_trace(request_id="request-1", metadata={"threadId": "thread-1"})
    run_id = uuid4()
    asyncio.run(callback.on_tool_start(
        {"name": "search_places"},
        {"query": "Hue", "api_key": "secret"},
        run_id=run_id,
    ))
    asyncio.run(callback.on_tool_end({"places": ["Citadel"]}, run_id=run_id))

    item = asyncio.run(service.list_records("observations", page=1, limit=25)).items[0]
    assert "secret" not in item["inputPreview"]
    assert item["outputPreview"]
    assert item["status"] == "success"


def test_service_completes_trace_and_reports_status(tmp_path, caplog) -> None:
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    service.start_trace(request_id="request-1", metadata={})
    with caplog.at_level(logging.INFO):
        asyncio.run(service.record_agent_invoke(
            request_id="request-1", route="explorer", success=False,
            message_length=10, warning_count=1, source_count=2,
            has_itinerary=False, error_code="TIMEOUT", duration_ms=123.4,
            output={"response": "failed"},
        ))

    result = asyncio.run(service.status())
    trace = asyncio.run(service.get_trace("request-1"))
    assert result.trace_count == 1
    assert result.error_count == 1
    assert trace is not None
    assert trace["durationMs"] == 123.4
    assert trace["errorCode"] == "TIMEOUT"
    assert '"response": "failed"' in trace["outputPreview"]
    assert (
        "agent_request_timing request_id=request-1 route=explorer "
        "status=error duration_ms=123.40"
    ) in caplog.messages


def test_local_store_reloads_persisted_traces(tmp_path) -> None:
    path = tmp_path / "observability" / "traces.json"
    first = LocalObservabilityStore(storage_path=path)
    first.start_trace("request-1", {"threadId": "thread-1"})
    first.complete_trace("request-1", success=True, route="explorer")

    second = LocalObservabilityStore(storage_path=path)
    trace = second.trace("request-1")
    assert trace is not None
    assert trace["status"] == "success"


def test_traced_call_is_nested_and_keeps_only_safe_summaries(
    tmp_path, caplog
) -> None:
    class State(TypedDict):
        count: int

    async def node(state: State) -> dict:
        value = await traced_call(
            "places.search",
            lambda: asyncio.sleep(0, result=state["count"] + 1),
            kind="tool",
            input_summary={"queryChars": 12},
            output_summary=lambda result: {"resultCount": result},
        )
        return {"count": value}

    builder = StateGraph(State)
    builder.add_node("place_checker", node)
    builder.add_edge(START, "place_checker")
    builder.add_edge("place_checker", END)
    graph = builder.compile()
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    callback = service.start_trace(request_id="request-1", metadata={})

    with caplog.at_level(logging.INFO):
        result = asyncio.run(
            graph.ainvoke({"count": 1}, config={"callbacks": [callback]})
        )
    trace = asyncio.run(service.get_trace("request-1"))

    assert result == {"count": 2}
    assert trace is not None
    tool = next(item for item in trace["observations"] if item["name"] == "places.search")
    assert tool["kind"] == "tool"
    assert tool["parentId"] is not None
    assert '"queryChars": 12' in tool["inputPreview"]
    assert '"resultCount": 2' in tool["outputPreview"]
    assert trace["observationCount"] == 3
    stage_log = next(
        message for message in caplog.messages
        if message.startswith("agent_stage_timing")
    )
    assert "request_id=request-1" in stage_log
    assert "stage=place_checker" in stage_log
    assert "status=success" in stage_log
    assert "duration_ms=" in stage_log


def test_observation_page_can_be_filtered_by_trace(tmp_path) -> None:
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    first = service.start_trace(request_id="request-1", metadata={})
    second = service.start_trace(request_id="request-2", metadata={})
    asyncio.run(first.on_tool_start({"name": "first"}, {}, run_id=uuid4()))
    asyncio.run(second.on_tool_start({"name": "second"}, {}, run_id=uuid4()))

    page = asyncio.run(
        service.list_records(
            "observations", page=1, limit=25, trace_id="request-2"
        )
    )

    assert len(page.items) == 1
    assert page.items[0]["traceId"] == "request-2"


def test_concurrent_graph_calls_do_not_mix_tool_spans(tmp_path) -> None:
    class State(TypedDict):
        label: str

    async def node(state: State) -> dict:
        await traced_call(
            "provider.call",
            lambda: asyncio.sleep(0.01, result=state["label"]),
            kind="tool",
            input_summary={"label": state["label"]},
            output_summary=lambda value: {"label": value},
        )
        return {}

    builder = StateGraph(State)
    builder.add_node("module", node)
    builder.add_edge(START, "module")
    builder.add_edge("module", END)
    graph = builder.compile()
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)

    async def invoke(request_id: str, label: str) -> None:
        callback = service.start_trace(request_id=request_id, metadata={})
        await graph.ainvoke({"label": label}, config={"callbacks": [callback]})

    async def run_both() -> None:
        await asyncio.gather(invoke("request-a", "alpha"), invoke("request-b", "beta"))

    asyncio.run(run_both())
    first = store.trace("request-a")
    second = store.trace("request-b")
    assert first is not None and second is not None
    first_tool = next(item for item in first["observations"] if item["kind"] == "tool")
    second_tool = next(item for item in second["observations"] if item["kind"] == "tool")
    assert "alpha" in first_tool["inputPreview"]
    assert "beta" not in first_tool["inputPreview"]
    assert "beta" in second_tool["inputPreview"]


def test_failed_tool_call_is_recorded_without_swallowing_error(tmp_path) -> None:
    class State(TypedDict):
        value: int

    async def fail() -> int:
        raise RuntimeError("provider payload must not be copied")

    async def node(_: State) -> dict:
        await traced_call(
            "provider.fail",
            fail,
            kind="tool",
            input_summary={"attempt": 1},
        )
        return {}

    builder = StateGraph(State)
    builder.add_node("module", node)
    builder.add_edge(START, "module")
    builder.add_edge("module", END)
    graph = builder.compile()
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    callback = service.start_trace(request_id="request-error", metadata={})

    with pytest.raises(RuntimeError, match="provider payload"):
        asyncio.run(
            graph.ainvoke({"value": 1}, config={"callbacks": [callback]})
        )

    trace = store.trace("request-error")
    assert trace is not None
    failed = next(item for item in trace["observations"] if item["name"] == "provider.fail")
    assert failed["status"] == "error"
    assert failed["error"] == "RuntimeError"
    assert "provider payload" not in (failed["outputPreview"] or "")
