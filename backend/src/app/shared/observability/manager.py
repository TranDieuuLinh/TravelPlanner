from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.shared.observability.callback import TraceCallbackHandler
from app.shared.observability.langfuse_adapter import (
    LangfuseObservabilityAdapter,
    NoOpObservabilityClient,
)
from app.shared.observability.ports import ObservabilityClient
from app.shared.observability.traced import (
    reset_current_trace_callback,
    set_current_trace_callback,
)


class ObservabilityManager:
    """Unified observability manager managing local store and Langfuse Cloud."""

    def __init__(
        self,
        *,
        client: ObservabilityClient | None = None,
        local_store: Any = None,
        release: str | None = None,
        environment: str | None = None,
    ) -> None:
        self.client = client or NoOpObservabilityClient()
        self.local_store = local_store
        self.release = release
        self.environment = environment
        self._active_traces: dict[str, Any] = {}
        self._trace_tokens: dict[str, Any] = {}

    def start_trace(
        self,
        *,
        request_id: str,
        name: str = "travelplanner.request",
        metadata: dict[str, Any] | None = None,
    ) -> TraceCallbackHandler:
        meta = metadata or {}
        thread_id = meta.get("threadId")
        user_id = meta.get("userId")
        entry_point = meta.get("entryPoint", name)

        # Local diagnostic store
        if self.local_store is not None:
            self.local_store.start_trace(request_id, meta)

        # Langfuse Cloud trace
        lf_trace = None
        if self.client.is_enabled:
            tags = [f"env:{self.environment or 'development'}"]
            if "route" in meta:
                tags.append(f"route:{meta['route']}")
            lf_trace = self.client.create_trace(
                trace_id=request_id,
                name=entry_point,
                session_id=thread_id,
                user_id=str(user_id) if user_id is not None else None,
                metadata=meta,
                tags=tags,
                input_data=meta.get("input"),
                release=self.release,
                environment=self.environment,
            )
            self._active_traces[request_id] = lf_trace

        callback = TraceCallbackHandler(
            request_id=request_id,
            local_store=self.local_store,
            langfuse_trace=lf_trace,
        )
        self._trace_tokens[request_id] = set_current_trace_callback(callback)
        return callback

    async def record_agent_invoke(
        self,
        *,
        request_id: str,
        route: str | None,
        success: bool,
        message_length: int,
        warning_count: int,
        source_count: int,
        has_itinerary: bool,
        error_code: str | None = None,
        duration_ms: float | None = None,
        output: Any = None,
    ) -> None:
        # Local store update
        if self.local_store is not None:
            self.local_store.complete_trace(
                request_id,
                route=route,
                success=success,
                message_length=message_length,
                warning_count=warning_count,
                source_count=source_count,
                has_itinerary=has_itinerary,
                error_code=error_code,
                duration_ms=duration_ms,
                output=output,
            )

        # Langfuse trace update
        lf_trace = self._active_traces.pop(request_id, None)
        if lf_trace is not None:
            tags = [f"env:{self.environment or 'development'}"]
            if route:
                tags.append(f"route:{route}")
            tags.append("status:success" if success else "status:error")
            lf_trace.update(
                output=output,
                metadata={
                    "route": route,
                    "success": success,
                    "durationMs": duration_ms,
                    "errorCode": error_code,
                    "warningCount": warning_count,
                    "sourceCount": source_count,
                    "hasItinerary": has_itinerary,
                },
                tags=tags,
            )
            lf_trace.end()
        token = self._trace_tokens.pop(request_id, None)
        if token is not None:
            reset_current_trace_callback(token)

    def get_status(self) -> dict[str, Any]:
        local_status = self.local_store.status() if self.local_store else {}
        return {
            **local_status,
            "langfuseEnabled": self.client.is_enabled,
        }

    async def flush(self, timeout_seconds: float | None = None) -> None:
        if self.client.is_enabled:
            await self.client.flush(timeout_seconds=timeout_seconds)

    async def shutdown(self, timeout_seconds: float | None = None) -> None:
        for token in self._trace_tokens.values():
            reset_current_trace_callback(token)
        self._trace_tokens.clear()
        for trace in self._active_traces.values():
            trace.end()
        self._active_traces.clear()
        if self.client.is_enabled:
            await self.client.shutdown(timeout_seconds=timeout_seconds)


def create_observability_manager(
    settings: Settings | None = None,
    *,
    local_store: Any = None,
) -> ObservabilityManager:
    s = settings or get_settings()
    client: ObservabilityClient
    if s.langfuse_enabled and s.langfuse_public_key and s.langfuse_secret_key:
        client = LangfuseObservabilityAdapter(
            enabled=s.langfuse_enabled,
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_base_url or s.langfuse_host,
            timeout_seconds=s.langfuse_timeout_seconds,
            flush_timeout_seconds=s.langfuse_flush_timeout_seconds,
            sample_rate=s.langfuse_sample_rate,
            release=s.langfuse_release or "0.1.0",
            environment=s.langfuse_environment or s.app_env,
            capture_input_output=s.langfuse_capture_input_output,
            max_captured_chars=s.langfuse_max_captured_chars,
            debug=s.langfuse_debug,
        )
    else:
        client = NoOpObservabilityClient()

    return ObservabilityManager(
        client=client,
        local_store=local_store,
        release=s.langfuse_release or "0.1.0",
        environment=s.langfuse_environment or s.app_env,
    )
