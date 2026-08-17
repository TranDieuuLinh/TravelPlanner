from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from app.shared.observability.ports import (
    ObservabilityGeneration,
    ObservabilitySpan,
    ObservabilityTrace,
)
from app.shared.observability.redaction import safe_preview


class TraceCallbackHandler(AsyncCallbackHandler):
    """LangChain / LangGraph callback handler connecting local store and Langfuse."""

    def __init__(
        self,
        request_id: str,
        *,
        local_store: Any = None,
        langfuse_trace: ObservabilityTrace | None = None,
    ) -> None:
        self.request_id = request_id
        self._local_store = local_store
        self._langfuse_trace = langfuse_trace
        self._local_observations: dict[UUID, str] = {}
        self._langfuse_observations: dict[UUID, ObservabilitySpan | ObservabilityGeneration] = {}
        self._start_times: dict[UUID, datetime] = {}

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        kind = _extract_trace_kind("chain", kwargs)
        name = _extract_run_name(kind, serialized, kwargs)
        self._start_observation(
            kind=kind,
            name=name,
            run_id=run_id,
            parent_run_id=parent_run_id,
            inputs=inputs,
            kwargs=kwargs,
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = _extract_run_name("tool", serialized, kwargs)
        self._start_observation(
            kind="tool",
            name=name,
            run_id=run_id,
            parent_run_id=parent_run_id,
            inputs=input_str,
            kwargs=kwargs,
        )

    async def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = _extract_run_name("llm", serialized, kwargs)
        self._start_observation(
            kind="llm",
            name=name,
            run_id=run_id,
            parent_run_id=parent_run_id,
            inputs=prompts,
            kwargs=kwargs,
        )

    async def on_chain_end(
        self,
        outputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, output_value=outputs)

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, output_value=output)

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, output_value=response)

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, error=error)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, error=error)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._finish_observation(run_id, error=error)

    async def flush(self) -> None:
        pass

    def _start_observation(
        self,
        *,
        kind: str,
        name: str,
        run_id: UUID,
        parent_run_id: UUID | None,
        inputs: Any,
        kwargs: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        self._start_times[run_id] = now

        # Local diagnostic store
        if self._local_store is not None:
            parent_obs_id = self._local_observations.get(parent_run_id) if parent_run_id else None
            obs_id = self._local_store.start_observation(
                self.request_id,
                kind,
                name,
                parent_obs_id,
                safe_preview(inputs, max_chars=2000),
            )
            self._local_observations[run_id] = obs_id

        # Langfuse Cloud adapter
        if self._langfuse_trace is not None:
            metadata = dict(kwargs.get("metadata") or {})
            parent_entry = (
                self._langfuse_observations.get(parent_run_id)
                if parent_run_id
                else None
            )
            parent_lf = parent_entry[0] if parent_entry else None
            creator = parent_lf if parent_lf is not None else self._langfuse_trace

            if kind == "llm":
                model = metadata.get("model") or kwargs.get("model") or "gemini"
                model_params = {
                    k: v
                    for k, v in metadata.items()
                    if k in {"temperature", "max_output_tokens", "structuredOutput"}
                }
                gen = creator.generation(
                    id=str(run_id),
                    name=name,
                    model=model,
                    model_parameters=model_params or None,
                    input=inputs,
                    metadata=metadata,
                    start_time=now,
                )
                self._langfuse_observations[run_id] = (gen, "llm")
            else:
                metadata.setdefault("observationType", kind)
                span = creator.span(
                    id=str(run_id),
                    name=name,
                    input=inputs,
                    metadata=metadata,
                    start_time=now,
                )
                self._langfuse_observations[run_id] = (span, "span")

    def _finish_observation(
        self,
        run_id: UUID,
        error: BaseException | None = None,
        output_value: Any = None,
    ) -> None:
        now = datetime.now(timezone.utc)

        # Local diagnostic store
        if self._local_store is not None:
            obs_id = self._local_observations.pop(run_id, None)
            if obs_id:
                self._local_store.finish_observation(
                    self.request_id,
                    obs_id,
                    error,
                    safe_preview(output_value, max_chars=2000),
                )

        # Langfuse Cloud adapter
        lf_entry = self._langfuse_observations.pop(run_id, None)
        if lf_entry is not None:
            lf_obs, kind = lf_entry
            level = "ERROR" if error is not None else "DEFAULT"
            status_msg = str(error) if error is not None else None

            usage = None
            if isinstance(output_value, dict):
                usage = output_value.get("usage")

            if hasattr(lf_obs, "end"):
                if kind == "llm":
                    lf_obs.end(
                        output=output_value,
                        usage=usage,
                        level=level,
                        status_message=status_msg,
                        end_time=now,
                    )
                else:
                    lf_obs.end(
                        output=output_value,
                        level=level,
                        status_message=status_msg,
                        end_time=now,
                    )
        self._start_times.pop(run_id, None)


def _extract_run_name(kind: str, serialized: Any, kwargs: dict[str, Any]) -> str:
    if isinstance(kwargs.get("name"), str) and kwargs["name"]:
        return kwargs["name"]
    if isinstance(kwargs.get("run_name"), str) and kwargs["run_name"]:
        return kwargs["run_name"]
    if isinstance(serialized, dict):
        name = serialized.get("name")
        if isinstance(name, str) and name:
            return name
        identifier = serialized.get("id")
        if isinstance(identifier, list) and identifier:
            return str(identifier[-1])
    return kind


def _extract_trace_kind(default: str, kwargs: dict[str, Any]) -> str:
    for tag in kwargs.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("trace_kind:"):
            value = tag.removeprefix("trace_kind:").strip()
            if value:
                return value
    return default
