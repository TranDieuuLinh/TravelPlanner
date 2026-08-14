from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from app.modules.observability.local_store import LocalObservabilityStore


class LocalTraceCallback(AsyncCallbackHandler):
    """Capture bounded LangGraph step timings and tool previews."""

    def __init__(self, store: LocalObservabilityStore, request_id: str) -> None:
        self.store = store
        self.request_id = request_id
        self._observations: dict[UUID, str] = {}

    async def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self._start(_trace_kind("chain", kwargs), serialized, run_id, parent_run_id, kwargs, inputs)

    async def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        self._start("llm", serialized, run_id, parent_run_id, kwargs, prompts)

    async def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        self._start("tool", serialized, run_id, parent_run_id, kwargs, input_str)

    async def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._finish(run_id, output_value=outputs)

    async def on_llm_end(self, response, *, run_id, **kwargs):
        self._finish(run_id, output_value=response)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish(run_id, output_value=output)

    async def on_chain_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error)

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error)

    async def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error)

    async def flush(self) -> None:
        return None

    def _start(self, kind: str, serialized: Any, run_id: UUID, parent_run_id, kwargs: dict[str, Any], input_value: Any = None) -> None:
        observation_id = self.store.start_observation(self.request_id, kind, _run_name(kind, serialized, kwargs), self._observations.get(parent_run_id), input_value)
        self._observations[run_id] = observation_id

    def _finish(self, run_id: UUID, error: BaseException | None = None, output_value: Any = None) -> None:
        observation_id = self._observations.pop(run_id, None)
        if observation_id:
            self.store.finish_observation(self.request_id, observation_id, error, output_value)


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


def _trace_kind(default: str, kwargs: dict[str, Any]) -> str:
    for tag in kwargs.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("trace_kind:"):
            value = tag.removeprefix("trace_kind:").strip()
            if value:
                return value
    return default
