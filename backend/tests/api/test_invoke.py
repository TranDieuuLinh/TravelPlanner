from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_graph
from app.main import create_app
from app.modules.information_finder.contract import (
    InformationFinderOutput,
    SourceReference,
)
from app.modules.supervisor.public import (
    SupervisorClassificationError,
    SupervisorDecision,
)


class FakeGraph:
    async def ainvoke(self, graph_input, config):
        return {
            "decision": SupervisorDecision(
                route="information_finder", reason="test", confidence=1.0
            ),
            "response": "Answer [1]",
            "information_output": InformationFinderOutput(
                answer="Answer [1]",
                sources=[
                    SourceReference(
                        source_id="source-1",
                        title="Museum",
                        url="https://example.test/museum",
                        updated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
                        date_kind="last_fetched_at",
                    )
                ],
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


def test_invoke_returns_finish_fields_in_camel_case():
    class FinishGraph:
        async def ainvoke(self, graph_input, config):
            return {
                "decision": SupervisorDecision(
                    route="finish",
                    reason="Greeting",
                    confidence=0.99,
                    response="Hello! I can help with travel.",
                    clarification_question="What would you like to plan?",
                    warnings=["No travel subgraph was needed."],
                ),
                "response": "Hello! I can help with travel.",
                "clarification_question": "What would you like to plan?",
                "warnings": ["No travel subgraph was needed."],
            }

    app = create_app()
    app.dependency_overrides[get_graph] = lambda: FinishGraph()
    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={"threadId": "thread-finish", "message": "Xin chào"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["clarificationQuestion"] == "What would you like to plan?"
    assert payload["warnings"] == ["No travel subgraph was needed."]
    assert "clarification_question" not in payload


def test_invoke_maps_disabled_supervisor_fallback_to_safe_service_error():
    class UnavailableGraph:
        async def ainvoke(self, graph_input, config):
            raise SupervisorClassificationError(
                "Supervisor intent classification failed and fallback is disabled."
            )

    app = create_app()
    app.dependency_overrides[get_graph] = lambda: UnavailableGraph()
    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={"threadId": "thread-error", "message": "Ambiguous request"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Supervisor intent classification failed and fallback is disabled."
    )
