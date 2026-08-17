from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Literal

from app.shared.observability.noop import NoOpGeneration, NoOpSpan
from app.shared.observability.ports import (
    ObservabilityGeneration,
    ObservabilitySpan,
    ObservabilityTrace,
)
from app.shared.observability.redaction import sanitize_payload

logger = logging.getLogger(__name__)


class _RateLimitedLogger:
    def __init__(self, interval_seconds: float = 30.0) -> None:
        self._interval_seconds = interval_seconds
        self._last_logged = 0.0
        self._suppressed_count = 0

    def warning(self, message: str, exc: Exception | None = None) -> None:
        now = time.monotonic()
        if now - self._last_logged >= self._interval_seconds:
            suppressed = (
                f" (suppressed {self._suppressed_count} similar errors)"
                if self._suppressed_count else ""
            )
            logger.warning("Langfuse error: %s%s: %s", message, suppressed, exc or "")
            self._last_logged = now
            self._suppressed_count = 0
        else:
            self._suppressed_count += 1


_err_log = _RateLimitedLogger()


class _LangfuseGenerationWrapper(ObservabilityGeneration):
    def __init__(self, raw: Any, max_chars: int, capture_io: bool, sdk_v4: bool) -> None:
        self._raw, self._max_chars, self._capture_io, self._sdk_v4 = raw, max_chars, capture_io, sdk_v4

    def end(self, *, output: Any = None, usage: dict[str, int] | None = None,
            level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
            status_message: str | None = None,
            end_time: datetime | None = None) -> None:
        try:
            kwargs: dict[str, Any] = {}
            if self._capture_io and output is not None:
                kwargs["output"] = sanitize_payload(output, max_chars=self._max_chars)
            if usage:
                kwargs["usage_details"] = usage
            if level:
                kwargs["level"] = level
            if status_message:
                kwargs["status_message"] = sanitize_payload(status_message, max_chars=self._max_chars)
            if self._sdk_v4:
                if kwargs:
                    self._raw.update(**kwargs)
                self._raw.end()
            else:
                kwargs["end_time"] = end_time or datetime.now(timezone.utc)
                self._raw.end(**kwargs)
        except Exception as exc:
            _err_log.warning("generation.end failed", exc)


class _LangfuseSpanWrapper(ObservabilitySpan):
    def __init__(self, raw: Any, max_chars: int, capture_io: bool, sdk_v4: bool) -> None:
        self._raw, self._max_chars, self._capture_io, self._sdk_v4 = raw, max_chars, capture_io, sdk_v4

    def span(self, *, id: str | None = None, name: str, input: Any = None,
             metadata: dict[str, Any] | None = None,
             start_time: datetime | None = None) -> ObservabilitySpan:
        try:
            safe_in = sanitize_payload(input, max_chars=self._max_chars) if self._capture_io and input is not None else None
            safe_meta = sanitize_payload(metadata, max_chars=self._max_chars) if metadata else None
            if self._sdk_v4:
                child = self._raw.start_observation(name=name, as_type=_v4_observation_type(safe_meta), input=safe_in, metadata=safe_meta)
            else:
                child = self._raw.span(id=id, name=name, input=safe_in, metadata=safe_meta, start_time=start_time or datetime.now(timezone.utc))
            return _LangfuseSpanWrapper(child, self._max_chars, self._capture_io, self._sdk_v4)
        except Exception as exc:
            _err_log.warning("span.span failed", exc)
            return NoOpSpan()

    def generation(self, *, id: str | None = None, name: str,
                   model: str | None = None,
                   model_parameters: dict[str, Any] | None = None,
                   input: Any = None,
                   metadata: dict[str, Any] | None = None,
                   start_time: datetime | None = None) -> ObservabilityGeneration:
        try:
            safe_in = sanitize_payload(input, max_chars=self._max_chars) if self._capture_io and input is not None else None
            safe_meta = sanitize_payload(metadata, max_chars=self._max_chars) if metadata else None
            if self._sdk_v4:
                child = self._raw.start_observation(name=name, as_type="generation", model=model, model_parameters=model_parameters, input=safe_in, metadata=safe_meta)
            else:
                child = self._raw.generation(id=id, name=name, model=model, model_parameters=model_parameters, input=safe_in, metadata=safe_meta, start_time=start_time or datetime.now(timezone.utc))
            return _LangfuseGenerationWrapper(child, self._max_chars, self._capture_io, self._sdk_v4)
        except Exception as exc:
            _err_log.warning("span.generation failed", exc)
            return NoOpGeneration()

    def end(self, *, output: Any = None,
            level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
            status_message: str | None = None,
            end_time: datetime | None = None) -> None:
        try:
            kwargs: dict[str, Any] = {}
            if self._capture_io and output is not None:
                kwargs["output"] = sanitize_payload(output, max_chars=self._max_chars)
            if level:
                kwargs["level"] = level
            if status_message:
                kwargs["status_message"] = sanitize_payload(status_message, max_chars=self._max_chars)
            if self._sdk_v4:
                if kwargs:
                    self._raw.update(**kwargs)
                self._raw.end()
            else:
                kwargs["end_time"] = end_time or datetime.now(timezone.utc)
                self._raw.end(**kwargs)
        except Exception as exc:
            _err_log.warning("span.end failed", exc)


class _LangfuseTraceWrapper(ObservabilityTrace):
    def __init__(self, trace_id: str, raw: Any, max_chars: int, capture_io: bool,
                 sdk_v4: bool, root_context: Any = None,
                 attributes_context: Any = None) -> None:
        self._trace_id, self._raw = trace_id, raw
        self._max_chars, self._capture_io, self._sdk_v4 = max_chars, capture_io, sdk_v4
        self._root_context, self._attributes_context = root_context, attributes_context
        self._ended = False

    @property
    def id(self) -> str:
        return self._trace_id

    def span(self, *, id: str | None = None, name: str, input: Any = None,
             metadata: dict[str, Any] | None = None,
             start_time: datetime | None = None) -> ObservabilitySpan:
        try:
            safe_in = sanitize_payload(input, max_chars=self._max_chars) if self._capture_io and input is not None else None
            safe_meta = sanitize_payload(metadata, max_chars=self._max_chars) if metadata else None
            if self._sdk_v4:
                child = self._raw.start_observation(name=name, as_type=_v4_observation_type(safe_meta), input=safe_in, metadata=safe_meta)
            else:
                child = self._raw.span(id=id, name=name, input=safe_in, metadata=safe_meta, start_time=start_time or datetime.now(timezone.utc))
            return _LangfuseSpanWrapper(child, self._max_chars, self._capture_io, self._sdk_v4)
        except Exception as exc:
            _err_log.warning("trace.span failed", exc)
            return NoOpSpan()

    def generation(self, *, id: str | None = None, name: str,
                   model: str | None = None,
                   model_parameters: dict[str, Any] | None = None,
                   input: Any = None,
                   metadata: dict[str, Any] | None = None,
                   start_time: datetime | None = None) -> ObservabilityGeneration:
        try:
            safe_in = sanitize_payload(input, max_chars=self._max_chars) if self._capture_io and input is not None else None
            safe_meta = sanitize_payload(metadata, max_chars=self._max_chars) if metadata else None
            if self._sdk_v4:
                child = self._raw.start_observation(name=name, as_type="generation", model=model, model_parameters=model_parameters, input=safe_in, metadata=safe_meta)
            else:
                child = self._raw.generation(id=id, name=name, model=model, model_parameters=model_parameters, input=safe_in, metadata=safe_meta, start_time=start_time or datetime.now(timezone.utc))
            return _LangfuseGenerationWrapper(child, self._max_chars, self._capture_io, self._sdk_v4)
        except Exception as exc:
            _err_log.warning("trace.generation failed", exc)
            return NoOpGeneration()

    def update(self, *, output: Any = None, metadata: dict[str, Any] | None = None,
               tags: list[str] | None = None) -> None:
        try:
            kwargs: dict[str, Any] = {}
            if output is not None and self._capture_io:
                kwargs["output"] = sanitize_payload(output, max_chars=self._max_chars)
            if metadata:
                kwargs["metadata"] = sanitize_payload(metadata, max_chars=self._max_chars)
            if tags:
                if self._sdk_v4:
                    kwargs.setdefault("metadata", {})
                    if isinstance(kwargs["metadata"], dict):
                        kwargs["metadata"]["traceTags"] = [str(t) for t in tags]
                else:
                    kwargs["tags"] = [str(t) for t in tags]
            if kwargs:
                self._raw.update(**kwargs)
        except Exception as exc:
            _err_log.warning("trace.update failed", exc)

    def end(self) -> None:
        try:
            # v4 root observations are spans and must be ended for the batch
            # exporter to emit the trace. Legacy trace objects have no end().
            end = getattr(self._raw, "end", None)
            if self._sdk_v4 and callable(end) and not self._ended:
                end()
                self._ended = True
                try:
                    if self._attributes_context is not None:
                        self._attributes_context.__exit__(None, None, None)
                finally:
                    if self._root_context is not None:
                        self._root_context.__exit__(None, None, None)
        except Exception as exc:
            _err_log.warning("trace.end failed", exc)


def _v4_observation_type(metadata: Any) -> str:
    if isinstance(metadata, dict):
        value = metadata.get("observationType") or metadata.get("kind")
        if value in {"tool", "agent", "chain", "retriever", "evaluator", "guardrail"}:
            return str(value)
    return "span"
