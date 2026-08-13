import asyncio
from uuid import uuid4

from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.service import ObservabilityService


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


def test_service_completes_trace_and_reports_status(tmp_path) -> None:
    store = LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    service = ObservabilityService(store)
    service.start_trace(request_id="request-1", metadata={})
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


def test_local_store_reloads_persisted_traces(tmp_path) -> None:
    path = tmp_path / "observability" / "traces.json"
    first = LocalObservabilityStore(storage_path=path)
    first.start_trace("request-1", {"threadId": "thread-1"})
    first.complete_trace("request-1", success=True, route="explorer")

    second = LocalObservabilityStore(storage_path=path)
    trace = second.trace("request-1")
    assert trace is not None
    assert trace["status"] == "success"
