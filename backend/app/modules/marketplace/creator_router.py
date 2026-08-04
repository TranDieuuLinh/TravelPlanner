from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.marketplace.dependencies import get_marketplace_service
from app.modules.marketplace.schema import (
    ListingCreateRequest,
    ListingDetailResponse,
    ListingUpdateRequest,
    PublishablePlanResponse,
)
from app.modules.marketplace.service import MarketplaceService
from app.modules.users.model import User

creator_router = APIRouter(prefix="/creator", tags=["creator-marketplace"])


@creator_router.get("/publishable-plans", response_model=list[PublishablePlanResponse])
def get_publishable_plans(
    user: Annotated[User, Depends(require_role("creator"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> list[PublishablePlanResponse]:
    return service.list_publishable_plans(user)


@creator_router.post("/listings", response_model=ListingDetailResponse, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: ListingCreateRequest,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.create_listing(user, payload)


@creator_router.get("/listings", response_model=list[ListingDetailResponse])
def get_creator_listings(
    user: Annotated[User, Depends(require_role("creator"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> list[ListingDetailResponse]:
    return service.get_creator_listings(user)


@creator_router.get("/listings/{listing_id}", response_model=ListingDetailResponse)
def get_creator_listing_detail(
    listing_id: str,
    user: Annotated[User, Depends(require_role("creator"))],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.get_creator_listing_detail(user, listing_id)


@creator_router.patch("/listings/{listing_id}", response_model=ListingDetailResponse)
def update_listing(
    listing_id: str,
    payload: ListingUpdateRequest,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.update_listing(user, listing_id, payload)


@creator_router.post("/listings/{listing_id}/submit", response_model=ListingDetailResponse)
def submit_listing(
    listing_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.submit_listing(user, listing_id)


@creator_router.post("/listings/{listing_id}/publish", response_model=ListingDetailResponse)
def publish_listing(
    listing_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.publish_listing(user, listing_id)


@creator_router.post("/listings/{listing_id}/unpublish", response_model=ListingDetailResponse)
def unpublish_listing(
    listing_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.unpublish_listing(user, listing_id)
