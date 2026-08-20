from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.api.dependencies import get_explorer_graph
from app.main import create_app
from app.modules.explorer.public import ExplorerOutput
from app.shared.observability.langfuse_adapter import LangfuseObservabilityAdapter
from app.shared.observability.manager import ObservabilityManager


def test_api_with_langfuse_disabled_works_normally() -> None:
    settings = Settings(
        app_env="test",
        langfuse_enabled=False,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_with_langfuse_enabled_traces_request_correlation() -> None:
    mock_lf_client = MagicMock()
    mock_trace = MagicMock()
    mock_lf_client.trace.return_value = mock_trace

    adapter = LangfuseObservabilityAdapter(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host="https://cloud.langfuse.com",
        client=mock_lf_client,
    )
    manager = ObservabilityManager(client=adapter, environment="test")

    settings = Settings(
        app_env="test",
        langfuse_enabled=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
    )
    app = create_app(settings)
    app.state.observability_service.manager = manager

    # Mock explorer graph dependency for fast isolated test
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "output": ExplorerOutput(
            status="ready",
            intake_id="intake-123",
            input_ADM="Huế",
            places=[],
            warnings=[],
        )
    }
    app.dependency_overrides[get_explorer_graph] = lambda: mock_graph

    client = TestClient(app)
    headers = {"x-trace-id": "trace-corr-12345"}
    payload = {
        "rawPrompt": "Du lịch Huế 3 ngày",
        "urls": [],
        "images": [],
    }

    response = client.post("/v1/explorer/invoke", json=payload, headers=headers)
    assert response.status_code == 200
    assert "status" not in response.json()

    # Verify trace created with correlation ID
    mock_lf_client.trace.assert_called_once()
    trace_kwargs = mock_lf_client.trace.call_args.kwargs
    assert trace_kwargs["id"] == "trace-corr-12345"

    # Verify trace updated on completion
    mock_trace.update.assert_called_once()
    update_kwargs = mock_trace.update.call_args.kwargs
    assert "route:explorer" in update_kwargs["tags"]
    assert "status:success" in update_kwargs["tags"]
