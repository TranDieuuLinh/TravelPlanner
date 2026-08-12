from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import get_settings
from app.modules.auth.public import require_admin
from app.modules.observability.adapters.langfuse_http import LangfuseHttpClient
from app.modules.observability.contract import LangfusePage, LangfuseStatus
from app.modules.observability.service import ObservabilityError, ObservabilityService


router = APIRouter(prefix="/admin/observability", tags=["admin-observability"])
Resource = Literal["traces", "observations", "sessions"]


def get_service(request: Request) -> ObservabilityService:
    service = getattr(request.app.state, "observability_service", None)
    if service is None:
        settings = get_settings()
        service = ObservabilityService(
            LangfuseHttpClient(
                settings.langfuse_host,
                settings.langfuse_public_key,
                settings.langfuse_secret_key,
                settings.langfuse_timeout_seconds,
            ),
            settings.langfuse_host,
        )
        request.app.state.observability_service = service
    return service


def handle(error: ObservabilityError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from None


@router.get("/status", response_model=LangfuseStatus)
async def status(
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[ObservabilityService, Depends(get_service)],
) -> LangfuseStatus:
    return await service.status()


@router.get("/{resource}", response_model=LangfusePage)
async def list_resource(
    resource: Resource,
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[ObservabilityService, Depends(get_service)],
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(25, ge=1, le=100),
) -> LangfusePage:
    try:
        return await service.list_records(resource, page=page, limit=limit)
    except ObservabilityError as error:
        handle(error)
