import asyncio
from uuid import uuid4

from app.modules.observability.langfuse_callback import LangfuseTraceCallback


class FakeClient:
    configured = True

    def __init__(self):
        self.payloads = []

    async def ingest(self, payload):
        self.payloads.append(payload)


def test_callback_flushes_trace_and_nested_spans():
    client = FakeClient()
    callback = LangfuseTraceCallback(client, trace_id="request-1", metadata={"requestId": "request-1"})
    parent = uuid4()
    child = uuid4()

    async def run():
        await callback.on_chain_start({"id": ["root"]}, {}, run_id=parent)
        await callback.on_chain_start({"id": ["node"]}, {}, run_id=child, parent_run_id=parent)
        await callback.on_chain_end({}, run_id=child)
        await callback.on_chain_end({}, run_id=parent)
        await callback.flush()

    asyncio.run(run())
    events = client.payloads[0]["batch"]
    assert events[0]["type"] == "trace-create"
    spans = [event for event in events if event["type"] == "span-create"]
    assert spans[1]["body"]["parentObservationId"] == spans[0]["body"]["id"]
    assert len([event for event in events if event["type"] == "span-update"]) == 2
