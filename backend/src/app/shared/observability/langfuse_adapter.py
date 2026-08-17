from __future__ import annotations

import asyncio
import hashlib
import random
from typing import Any

from app.shared.observability.noop import (
    NoOpGeneration,
    NoOpObservabilityClient,
    NoOpSpan,
    NoOpTrace,
)
from app.shared.observability.ports import ObservabilityClient, ObservabilityTrace
from app.shared.observability.redaction import sanitize_payload
from app.shared.observability.wrappers import _LangfuseTraceWrapper, _err_log


class LangfuseObservabilityAdapter(ObservabilityClient):
    """Resilient Langfuse Cloud adapter supporting SDK v4 and legacy v2 clients."""

    def __init__(self, *, enabled: bool = False, public_key: str | None = None,
                 secret_key: str | None = None,
                 host: str = "https://cloud.langfuse.com",
                 timeout_seconds: float = 10.0,
                 flush_timeout_seconds: float = 5.0,
                 sample_rate: float = 1.0,
                 release: str | None = None,
                 environment: str | None = None,
                 capture_input_output: bool = True,
                 max_captured_chars: int = 2000,
                 debug: bool = False,
                 client: Any = None) -> None:
        self._enabled = bool(enabled and public_key and secret_key)
        self._public_key, self._secret_key = public_key, secret_key
        self._host = host.rstrip("/")
        self._timeout, self._flush_timeout = timeout_seconds, flush_timeout_seconds
        self._sample_rate = max(0.0, min(1.0, sample_rate))
        self._release, self._environment = release, environment
        self._capture_io, self._max_chars, self._debug = capture_input_output, max_captured_chars, debug
        self._client = client
        self._sdk_v4 = self._detect_v4(client)
        if self._enabled and self._client is None:
            self._client = self._init_client()
            self._sdk_v4 = self._detect_v4(self._client)

    @staticmethod
    def _detect_v4(client: Any) -> bool:
        # MagicMock exposes every attribute, so the absence of legacy ``trace``
        # is part of detection and keeps existing v2-compatible tests stable.
        return bool(client and callable(getattr(client, "start_observation", None))
                    and not callable(getattr(client, "trace", None)))

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._client is not None

    def _init_client(self) -> Any:
        try:
            from langfuse import Langfuse
            return Langfuse(
                public_key=self._public_key,
                secret_key=self._secret_key,
                base_url=self._host,
                timeout=int(self._timeout),
                release=self._release,
                environment=self._environment,
                # Sampling happens once below; SDK sampling remains 1.0.
                sample_rate=1.0,
                debug=self._debug,
                tracing_enabled=True,
            )
        except Exception as exc:
            _err_log.warning("Failed to initialize Langfuse SDK", exc)
            self._enabled = False
            return None

    def create_trace(self, *, trace_id: str, name: str,
                     session_id: str | None = None,
                     user_id: str | None = None,
                     metadata: dict[str, Any] | None = None,
                     tags: list[str] | None = None,
                     input_data: Any = None,
                     release: str | None = None,
                     environment: str | None = None) -> ObservabilityTrace:
        if not self.is_enabled or (self._sample_rate < 1.0 and random.random() > self._sample_rate):
            return NoOpTrace(trace_id)
        try:
            safe_input = sanitize_payload(input_data, max_chars=self._max_chars) if self._capture_io and input_data is not None else None
            safe_meta = sanitize_payload(metadata, max_chars=self._max_chars) if metadata else None
            clean_tags = [str(tag) for tag in tags] if tags else None
            version = release or self._release
            root_context = None
            attributes_context = None
            if self._sdk_v4:
                v4_meta = dict(safe_meta or {})
                if session_id:
                    v4_meta["sessionId"] = str(session_id)
                if user_id:
                    v4_meta["userId"] = str(user_id)
                if clean_tags:
                    v4_meta["traceTags"] = clean_tags
                start_current = getattr(self._client, "start_as_current_observation", None)
                if callable(start_current):
                    root_context = start_current(
                        name=name,
                        as_type="span",
                        trace_context={"trace_id": _normalize_trace_id(trace_id)},
                        input=safe_input,
                        metadata=v4_meta or None,
                        version=version,
                        end_on_exit=False,
                    )
                    raw = root_context.__enter__()
                    try:
                        from langfuse import propagate_attributes
                        attributes_context = propagate_attributes(
                            user_id=str(user_id) if user_id else None,
                            session_id=str(session_id) if session_id else None,
                            metadata=v4_meta or None,
                            version=version,
                            tags=clean_tags,
                            trace_name=name,
                            environment=environment or self._environment,
                        )
                        attributes_context.__enter__()
                    except Exception:
                        if root_context is not None:
                            root_context.__exit__(None, None, None)
                        raise
                else:
                    raw = self._client.start_observation(
                        name=name,
                        as_type="span",
                        trace_context={"trace_id": _normalize_trace_id(trace_id)},
                        input=safe_input,
                        metadata=v4_meta or None,
                        version=version,
                    )
            else:
                raw = self._client.trace(
                    id=trace_id, name=name, session_id=session_id, user_id=user_id,
                    metadata=safe_meta, tags=clean_tags, input=safe_input,
                    release=version, version=version,
                )
            return _LangfuseTraceWrapper(
                trace_id, raw, self._max_chars, self._capture_io, self._sdk_v4,
                root_context, attributes_context,
            )
        except Exception as exc:
            _err_log.warning("create_trace failed", exc)
            return NoOpTrace(trace_id)

    async def flush(self, timeout_seconds: float | None = None) -> None:
        if not self.is_enabled:
            return
        try:
            await asyncio.wait_for(asyncio.to_thread(self._client.flush), timeout=timeout_seconds or self._flush_timeout)
        except asyncio.TimeoutError:
            _err_log.warning("Langfuse flush timed out")
        except Exception as exc:
            _err_log.warning("Langfuse flush failed", exc)

    async def shutdown(self, timeout_seconds: float | None = None) -> None:
        if not self.is_enabled:
            return
        try:
            shutdown = getattr(self._client, "shutdown", None) or self._client.flush
            await asyncio.wait_for(asyncio.to_thread(shutdown), timeout=timeout_seconds or self._flush_timeout)
        except asyncio.TimeoutError:
            _err_log.warning("Langfuse shutdown timed out")
        except Exception as exc:
            _err_log.warning("Langfuse shutdown failed", exc)


def _normalize_trace_id(trace_id: str) -> str:
    candidate = str(trace_id).replace("-", "").strip().lower()
    if len(candidate) == 32:
        try:
            int(candidate, 16)
            return candidate
        except ValueError:
            pass
    return hashlib.sha256(str(trace_id).encode("utf-8")).hexdigest()[:32]


__all__ = [
    "LangfuseObservabilityAdapter",
    "NoOpGeneration",
    "NoOpObservabilityClient",
    "NoOpSpan",
    "NoOpTrace",
]
