from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.observability.contract import LangfusePage, LangfuseStatus
from app.modules.observability.ports import LangfuseClient, LangfuseProviderError


class ObservabilityError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ObservabilityService:
    def __init__(self, client: LangfuseClient, host: str) -> None:
        self.client = client
        self.host = host

    async def status(self) -> LangfuseStatus:
        if not self.client.configured:
            return LangfuseStatus(
                configured=False,
                reachable=False,
                message="Thiếu LANGFUSE_PUBLIC_KEY hoặc LANGFUSE_SECRET_KEY.",
            )
        try:
            payload = await self.client.get("projects", {"limit": 1})
        except LangfuseProviderError as error:
            return LangfuseStatus(
                configured=True,
                reachable=False,
                message=error.message,
            )
        return LangfuseStatus(
            configured=True,
            reachable=True,
            message=f"Đã kết nối Langfuse tại {self.host}.",
            project_count=_total_from(payload),
        )

    async def list_records(self, resource: str, *, page: int, limit: int) -> LangfusePage:
        try:
            payload = await self.client.get(
                resource,
                {"page": page, "limit": limit},
            )
        except LangfuseProviderError as error:
            raise ObservabilityError(error.code, error.message, error.status_code) from error
        return _page_from_payload(payload, page=page, limit=limit)

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
    ) -> None:
        if not self.client.configured:
            return
        trace_id = uuid4().hex
        body = {
            "id": trace_id,
            "name": "travelplanner.agent.invoke",
            "metadata": {
                "requestId": request_id,
                "route": route,
                "success": success,
                "messageLength": message_length,
                "warningCount": warning_count,
                "sourceCount": source_count,
                "hasItinerary": has_itinerary,
                "errorCode": error_code,
            },
        }
        try:
            await self.client.ingest(
                {
                    "batch": [
                        {
                            "id": uuid4().hex,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "type": "trace-create",
                            "body": body,
                        }
                    ]
                }
            )
        except LangfuseProviderError:
            # Observability must never make an agent request fail.
            return


def _page_from_payload(payload: dict[str, Any], *, page: int, limit: int) -> LangfusePage:
    raw_items = payload.get("data", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    total = _total_from(payload)
    total_pages = _as_int(meta.get("totalPages"))
    has_more = page < total_pages if total_pages is not None else (len(items) >= limit)
    return LangfusePage(
        items=items,
        page=_as_int(meta.get("page")) or page,
        limit=_as_int(meta.get("limit")) or limit,
        total=total,
        has_more=has_more,
    )


def _total_from(payload: dict[str, Any]) -> int | None:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    for key in ("totalItems", "total", "count"):
        value = _as_int(meta.get(key))
        if value is not None:
            return value
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
