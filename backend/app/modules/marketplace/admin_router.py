from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.marketplace.dependencies import get_marketplace_service
from app.modules.marketplace.schema import (
    AdminModerationReviewRequest,
    AdminRefundRequest,
    AuditEventResponse,
    ListingVersionResponse,
    ReportResolveRequest,
    ReportResponse,
)
from app.modules.marketplace.service import MarketplaceService
from app.modules.users.model import User

admin_router = APIRouter(prefix="/admin", tags=["admin-marketplace"])


@admin_router.get("/listings/pending")
def get_pending_listings(
    admin: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> list[dict]:
    return service.get_admin_pending_listings(admin)


@admin_router.post("/listings/{version_id}/review", response_model=ListingVersionResponse)
def review_listing_version(
    version_id: str,
    payload: AdminModerationReviewRequest,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingVersionResponse:
    # Double check admin role inside require_csrf context
    require_role("admin")(admin)
    return service.review_listing_version(admin, version_id, payload)


@admin_router.get("/reports", response_model=list[ReportResponse])
def get_admin_reports(
    admin: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    status: str | None = Query(default=None),
    reason: str | None = Query(default=None),
) -> list[ReportResponse]:
    return service.get_admin_reports(admin, status=status, reason=reason)


@admin_router.post("/reports/{report_id}/resolve", response_model=ReportResponse)
def resolve_report(
    report_id: str,
    payload: ReportResolveRequest,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ReportResponse:
    require_role("admin")(admin)
    return service.resolve_report(admin, report_id, payload)


@admin_router.post("/orders/{order_id}/refund")
def refund_order(
    order_id: str,
    payload: AdminRefundRequest,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> dict:
    require_role("admin")(admin)
    return service.admin_refund_order(admin, order_id, reason=payload.reason)


@admin_router.get("/audit-events", response_model=list[AuditEventResponse])
def get_admin_audit_events(
    admin: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    actorId: int | None = Query(default=None, alias="actorId"),
    action: str | None = Query(default=None),
    resourceType: str | None = Query(default=None, alias="resourceType"),
    resourceId: str | None = Query(default=None, alias="resourceId"),
) -> list[AuditEventResponse]:
    return service.get_admin_audit_events(
        admin,
        actor_id=actorId,
        action=action,
        resource_type=resourceType,
        resource_id=resourceId,
    )

