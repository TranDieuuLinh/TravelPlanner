import logging
from typing import Any

from app.modules.observability.contract import ObservabilityPage, ObservabilityStatus
from app.modules.observability.local_callback import LocalTraceCallback
from app.modules.observability.local_store import LocalObservabilityStore

logger = logging.getLogger(__name__)


class ObservabilityError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ObservabilityService:
    def __init__(self, store: LocalObservabilityStore | None = None) -> None:
        self.store = store or LocalObservabilityStore()

    def start_trace(self, *, request_id: str, metadata: dict[str, Any]) -> LocalTraceCallback:
        self.store.start_trace(request_id, metadata)
        return LocalTraceCallback(self.store, request_id)

    async def status(self) -> ObservabilityStatus:
        return ObservabilityStatus(**self.store.status())

    async def list_records(
        self,
        resource: str,
        *,
        page: int,
        limit: int,
        trace_id: str | None = None,
    ) -> ObservabilityPage:
        return ObservabilityPage(
            **self.store.page(resource, page, limit, trace_id=trace_id)
        )

    async def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        return self.store.trace(trace_id)

    async def record_agent_invoke(
        self, *, request_id: str, route: str | None, success: bool,
        message_length: int, warning_count: int, source_count: int,
        has_itinerary: bool, error_code: str | None = None,
        duration_ms: float | None = None,
        output: Any = None,
    ) -> None:
        self.store.complete_trace(
            request_id, route=route, success=success,
            message_length=message_length, warning_count=warning_count,
            source_count=source_count, has_itinerary=has_itinerary,
            error_code=error_code, duration_ms=duration_ms, output=output,
        )
        logger.info(
            "agent_request_timing request_id=%s route=%s status=%s duration_ms=%s",
            request_id,
            route or "unknown",
            "success" if success else "error",
            f"{duration_ms:.2f}" if duration_ms is not None else "unknown",
        )
