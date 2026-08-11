import asyncio

from app.modules.observability.service import ObservabilityService


class FakeLangfuseClient:
    configured = True

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    async def get(self, resource, params):
        self.calls.append((resource, params))
        return self.payload

    async def ingest(self, payload):
        self.calls.append(("ingest", payload))


def test_list_records_normalizes_langfuse_page() -> None:
    client = FakeLangfuseClient(
        {
            "data": [{"id": "trace-1", "name": "planner"}],
            "meta": {"page": 2, "limit": 25, "totalItems": 51, "totalPages": 3},
        }
    )

    result = asyncio.run(
        ObservabilityService(client, "http://localhost:3005").list_records(
            "traces", page=2, limit=25
        )
    )

    assert result.items[0]["id"] == "trace-1"
    assert result.page == 2
    assert result.total == 51
    assert result.has_more is True


def test_status_reports_missing_keys_without_calling_provider() -> None:
    client = FakeLangfuseClient({})
    client.configured = False

    result = asyncio.run(ObservabilityService(client, "http://localhost:3005").status())

    assert result.configured is False
    assert result.reachable is False
    assert client.calls == []


def test_record_agent_invoke_sends_safe_trace_metadata() -> None:
    client = FakeLangfuseClient({})

    asyncio.run(
        ObservabilityService(client, "http://localhost:3005").record_agent_invoke(
            request_id="request-1",
            route="explorer",
            success=True,
            message_length=42,
            warning_count=1,
            source_count=2,
            has_itinerary=True,
        )
    )

    event = client.calls[0][1]["batch"][0]
    assert event["type"] == "trace-create"
    assert event["body"]["metadata"] == {
        "requestId": "request-1",
        "route": "explorer",
        "success": True,
        "messageLength": 42,
        "warningCount": 1,
        "sourceCount": 2,
        "hasItinerary": True,
        "errorCode": None,
    }
