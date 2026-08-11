from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langchain_core.callbacks import AsyncCallbackHandler

from app.modules.observability.ports import LangfuseClient, LangfuseProviderError


class LangfuseTraceCallback(AsyncCallbackHandler):
    """Collect LangGraph run callbacks and send them as one Langfuse batch."""

    def __init__(self, client: LangfuseClient, *, trace_id: str, metadata: dict[str, Any]):
        self.client = client
        self.trace_id = trace_id
        self.events: list[dict[str, Any]] = [
            _event(
                "trace-create",
                {
                    "id": trace_id,
                    "name": "travelplanner.agent.invoke",
                    "timestamp": _now(),
                    "metadata": metadata,
                },
            )
        ]
        self._observations: dict[UUID, str] = {}
        self._flushed = False

    async def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        await self._start_observation("chain", serialized, run_id, parent_run_id, kwargs)

    async def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        await self._start_observation("llm", serialized, run_id, parent_run_id, kwargs)

    async def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        await self._start_observation("tool", serialized, run_id, parent_run_id, kwargs)

    async def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._finish_observation(run_id)

    async def on_llm_end(self, response, *, run_id, **kwargs):
        self._finish_observation(run_id)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish_observation(run_id)

    async def on_chain_error(self, error, *, run_id, **kwargs):
        self._finish_observation(run_id, error=error)

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish_observation(run_id, error=error)

    async def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish_observation(run_id, error=error)

    async def flush(self) -> None:
        if self._flushed or not self.client.configured or len(self.events) <= 1:
            return
        try:
            await self.client.ingest({"batch": self.events})
        except LangfuseProviderError:
            # Tracing must never change the outcome of an agent request.
            return
        self._flushed = True

    async def _start_observation(self, kind, serialized, run_id, parent_run_id, kwargs):
        observation_id = uuid4().hex
        self._observations[run_id] = observation_id
        body = {
            "id": observation_id,
            "traceId": self.trace_id,
            "name": _run_name(kind, serialized, kwargs),
            "startTime": _now(),
        }
        if parent_run_id in self._observations:
            body["parentObservationId"] = self._observations[parent_run_id]
        self.events.append(_event("span-create", body))

    def _finish_observation(self, run_id: UUID, *, error: BaseException | None = None):
        observation_id = self._observations.pop(run_id, None)
        if observation_id is None:
            return
        body = {"id": observation_id, "traceId": self.trace_id, "endTime": _now()}
        if error is not None:
            body["statusMessage"] = type(error).__name__
            body["level"] = "ERROR"
        self.events.append(_event("span-update", body))


def _event(event_type: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "timestamp": _now(),
        "type": event_type,
        "body": body,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_name(kind: str, serialized: Any, kwargs: dict[str, Any]) -> str:
    if isinstance(kwargs.get("name"), str) and kwargs["name"]:
        return kwargs["name"]
    if isinstance(serialized, dict):
        name = serialized.get("name")
        if isinstance(name, str) and name:
            return name
        identifier = serialized.get("id")
        if isinstance(identifier, list) and identifier:
            return str(identifier[-1])
    return kind
