from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_explorer_graph, get_graph
from app.main import create_app
from app.modules.information_finder.contract import (
    InformationFinderOutput,
    SourceReference,
)
from app.modules.supervisor.public import (
    SupervisorClassificationError,
    SupervisorDecision,
)
from app.modules.itinerary_planner.public import ItineraryPlannerOutput
from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.service import ObservabilityService


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
    assert payload["contentBlocks"] == []
    assert "request_id" not in payload


def test_agent_invoke_forwards_force_refresh_to_root_graph():
    received = {}

    class CapturingGraph(FakeGraph):
        async def ainvoke(self, graph_input, config):
            received.update(graph_input)
            return await super().ainvoke(graph_input, config)

    app = create_app()
    app.dependency_overrides[get_graph] = lambda: CapturingGraph()
    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={
            "threadId": "thread-refresh",
            "message": "Tạo lịch trình chuyến đi từ liên kết này",
            "urls": ["https://example.test/post"],
            "forceRefresh": True,
        },
    )

    assert response.status_code == 200
    assert received["force_refresh"] is True


def test_agent_invoke_rejects_url_without_a_message():
    response = TestClient(create_app()).post(
        "/v1/agent/invoke",
        json={
            "threadId": "thread-url-without-message",
            "urls": ["https://example.test/post"],
        },
    )

    assert response.status_code == 422


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


def test_invoke_returns_planner_output_in_camel_case():
    class PlannerGraph:
        async def ainvoke(self, graph_input, config):
            return {
                "decision": SupervisorDecision(
                    route="explorer", reason="test", confidence=1.0
                ),
                "response": "Đã tạo lịch trình.",
                "planner_output": ItineraryPlannerOutput.model_validate(
                    {
                        "destination": "Hà Nội",
                        "timezone": "Asia/Ho_Chi_Minh",
                        "people": 2,
                        "days": [
                            {
                                "day": 1,
                                "date": "2026-08-22",
                                "stops": [
                                    {
                                        "itemId": "planner:1:ho-guom",
                                        "placeId": "ho-guom",
                                        "name": "Hồ Gươm",
                                        "kind": "place",
                                        "priority": "url",
                                        "startMinute": 480,
                                        "endMinute": 540,
                                        "durationMinutes": 60,
                                        "coordinates": {
                                            "latitude": 21.0285,
                                            "longitude": 105.8542,
                                        },
                                        "notes": {
                                            "text": "Nên đến trước 8 giờ.",
                                            "sourceType": "url",
                                            "sourceUrl": "https://example.test/video",
                                        },
                                        "personalNotes": "Nhớ mang ô.",
                                        "costPerPerson": 0,
                                    }
                                ],
                                "legs": [],
                                "activityMinutes": 60,
                                "travelMinutes": 0,
                                "costPerPerson": 0,
                                "costBreakdown": {
                                    "accommodation": 0,
                                    "food": 0,
                                    "localTransport": 0,
                                    "activities": 0,
                                    "misc": 0,
                                    "total": 0,
                                    "currency": "VND",
                                },
                            }
                        ],
                        "totalCostPerPerson": 0,
                        "currency": "VND",
                        "solver": {
                            "status": "OPTIMAL",
                            "optimalityProven": True,
                            "objectiveValue": 0,
                            "objectivePolicyVersion": "test-v1",
                            "objectiveComponents": {},
                            "passes": [],
                            "planningTimeMs": 1,
                        },
                        "unscheduled": [],
                        "discardedOptionalCount": 0,
                        "warnings": [],
                        "phaseTimingsMs": {"total": 1},
                    }
                ),
            }

    app = create_app()
    app.dependency_overrides[get_graph] = lambda: PlannerGraph()
    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={"threadId": "thread-planner", "message": "Đi Hà Nội"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["itinerary"] is None
    assert payload["plannerOutput"]["destination"] == "Hà Nội"
    note = payload["plannerOutput"]["days"][0]["stops"][0]["notes"]
    assert note == {
        "text": "Nên đến trước 8 giờ.",
        "sourceType": "url",
        "sourceUrl": "https://example.test/video",
    }
    assert payload["plannerOutput"]["days"][0]["stops"][0]["personalNotes"] == (
        "Nhớ mang ô."
    )
    assert "planner_output" not in payload


def test_invoke_maps_retryable_planner_failure_to_service_unavailable(tmp_path):
    class FailedPlannerGraph:
        async def ainvoke(self, graph_input, config):
            return {
                "decision": SupervisorDecision(
                    route="explorer", reason="test", confidence=1.0
                ),
                "response": (
                    "Itinerary planning stopped: "
                    "Route repair failed: CP-SAT priority pass returned UNKNOWN."
                ),
                "planner_error_code": "route_repair_unknown",
                "warnings": ["Route repair failed."],
            }

    app = create_app()
    app.state.observability_service = ObservabilityService(
        LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    )
    app.dependency_overrides[get_graph] = lambda: FailedPlannerGraph()

    response = TestClient(app).post(
        "/v1/agent/invoke",
        json={"threadId": "thread-planner-failed", "message": "Đi Hà Nội"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_REPAIR_UNKNOWN",
        "message": (
            "Itinerary planning stopped: "
            "Route repair failed: CP-SAT priority pass returned UNKNOWN."
        ),
        "retryable": True,
    }
    traces = app.state.observability_service.store.page("traces", 1, 25)["items"]
    assert traces[0]["success"] is False
    assert traces[0]["errorCode"] == "ROUTE_REPAIR_UNKNOWN"


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


def test_explorer_invoke_returns_full_explorer_contract(tmp_path):
    class ExplorerGraph:
        async def ainvoke(self, graph_input, config):
            from app.modules.explorer.public import ExplorerOutput

            assert graph_input["payload"].raw_prompt == "Lập kế hoạch ở Huế"
            assert graph_input["payload"].force_refresh is True
            assert config["callbacks"]
            return {
                "output": ExplorerOutput(
                    status="ready",
                    intakeId="intake-test",
                    input_ADM="Huế",
                )
            }

    app = create_app()
    app.state.observability_service = ObservabilityService(
        LocalObservabilityStore(storage_path=tmp_path / "traces.json")
    )
    app.dependency_overrides[get_explorer_graph] = lambda: ExplorerGraph()
    response = TestClient(app).post(
        "/v1/explorer/invoke",
        json={"rawPrompt": "Lập kế hoạch ở Huế", "forceRefresh": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "status" not in payload
    assert payload["input_ADM"] == "Huế"
    assert payload["days"] == 3
    assert "schemaVersion" not in payload
    assert "clarificationQuestion" not in payload
    assert "warnings" not in payload
    assert "completeness" not in payload
    assert "error" not in payload
    assert "urlNotes" not in payload
    traces = app.state.observability_service.store.page("traces", 1, 25)["items"]
    assert len(traces) == 1
    assert traces[0]["entryPoint"] == "explorer.invoke"
    assert "Lập kế hoạch" not in traces[0]["inputPreview"]
