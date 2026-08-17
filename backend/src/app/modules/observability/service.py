from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from app.modules.observability.contract import ObservabilityPage, ObservabilityStatus
from app.modules.observability.local_store import LocalObservabilityStore
from app.shared.observability import (
    ObservabilityManager,
    create_observability_manager,
)


class ObservabilityError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ObservabilityService:
    def __init__(
        self,
        store: LocalObservabilityStore | None = None,
        manager: ObservabilityManager | None = None,
    ) -> None:
        self.store = store or (manager.local_store if manager else None) or LocalObservabilityStore()
        self.manager = manager or create_observability_manager(local_store=self.store)

    def start_trace(self, *, request_id: str, metadata: dict[str, Any]) -> AsyncCallbackHandler:
        return self.manager.start_trace(request_id=request_id, metadata=metadata)

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
        await self.manager.record_agent_invoke(
            request_id=request_id,
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

    async def aclose(self) -> None:
        await self.manager.shutdown()
