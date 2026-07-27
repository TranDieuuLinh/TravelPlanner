from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.marketplace.dependencies import get_marketplace_service
from app.modules.marketplace.schema import (
    AdminModerationReviewRequest,
    ListingVersionResponse,
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
