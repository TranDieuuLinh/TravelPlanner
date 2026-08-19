from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.auth.public import require_admin
from app.modules.observability.contract import ObservabilityPage, ObservabilityStatus
from app.modules.observability.service import ObservabilityError, ObservabilityService


router = APIRouter(prefix="/admin/observability", tags=["admin-observability"])
Resource = Literal["traces", "observations", "sessions"]


def get_service(request: Request) -> ObservabilityService:
    service = getattr(request.app.state, "observability_service", None)
    if service is None:
        service = ObservabilityService()
        request.app.state.observability_service = service
    return service


def handle(error: ObservabilityError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from None


@router.get("/status", response_model=ObservabilityStatus)
async def status(
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[ObservabilityService, Depends(get_service)],
) -> ObservabilityStatus:
    return await service.status()


@router.get("/{resource}", response_model=ObservabilityPage)
async def list_resource(
    resource: Resource,
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[ObservabilityService, Depends(get_service)],
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(25, ge=1, le=100),
    trace_id: str | None = Query(None, alias="traceId"),
) -> ObservabilityPage:
    try:
        return await service.list_records(
            resource,
            page=page,
            limit=limit,
            trace_id=trace_id,
        )
    except ObservabilityError as error:
        handle(error)


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[ObservabilityService, Depends(get_service)],
) -> dict:
    trace = await service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail={"code": "TRACE_NOT_FOUND", "message": "Không tìm thấy trace."})
    return trace
