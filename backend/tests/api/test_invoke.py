from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_graph
from app.main import create_app
from app.modules.information_finder.contract import InformationFinderOutput, SourceReference
from app.modules.supervisor.public import SupervisorDecision


class FakeGraph:
    async def ainvoke(self, graph_input, config):
        return {
            "decision": SupervisorDecision(
                route="information_finder", reason="test", confidence=1.0
            ),
            "response": "Answer [1]",
            "information_output": InformationFinderOutput(
                answer="Answer [1]",
                sources=[SourceReference(
                    source_id="source-1",
                    title="Museum",
                    url="https://example.test/museum",
                    updated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
                    date_kind="last_fetched_at",
                )],
            ),
        }


def test_invoke_accepts_and_returns_camel_case_source_contract():
    app = create_app()
    app.dependency_overrides[get_graph] = lambda: FakeGraph()
    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={"threadId": "thread-1", "message": "museum hours"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requestId"]
    assert payload["sources"][0]["sourceId"] == "source-1"
    assert payload["sources"][0]["updatedAt"] == "2026-08-10T00:00:00Z"
    assert "request_id" not in payload
