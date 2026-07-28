from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import require_active_user, require_csrf
from app.modules.marketplace.dependencies import get_marketplace_service, get_optional_user
from app.modules.marketplace.schema import (
    BuyerPlanItemResponse,
    FavoriteResponse,
    ListingDetailResponse,
    ListingPaginatedResponse,
    ListingSummaryResponse,
    ReportCreateRequest,
    ReportResponse,
    ReviewCreateRequest,
    ReviewPaginatedResponse,
    ReviewResponse,
)
from app.modules.marketplace.service import MarketplaceService
from app.modules.users.model import User

public_router = APIRouter(prefix="", tags=["public-marketplace"])


@public_router.get("/listings", response_model=ListingPaginatedResponse)
def search_listings(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=12, ge=1, le=50, alias="pageSize"),
    query: str | None = None,
    category: str | None = None,
    minPrice: int | None = Query(default=None, alias="minPrice"),
    maxPrice: int | None = Query(default=None, alias="maxPrice"),
    sort: str = Query(default="newest"),
    user: Annotated[User | None, Depends(get_optional_user)] = None,
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)] = None,  # type: ignore
) -> ListingPaginatedResponse:
    return service.search_public_listings(
        user=user,
        page=page,
        page_size=pageSize,
        query=query,
        category=category,
        min_price=minPrice,
        max_price=maxPrice,
        sort=sort,
    )


@public_router.get("/listings/{listing_id}", response_model=ListingDetailResponse)
def get_listing_detail(
    listing_id: str,
    user: Annotated[User | None, Depends(get_optional_user)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ListingDetailResponse:
    return service.get_public_listing_detail(user, listing_id)


@public_router.put("/listings/{listing_id}/favorite", response_model=FavoriteResponse)
def add_favorite(
    listing_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> FavoriteResponse:
    service.set_favorite(user, listing_id, is_favorite=True)
    return FavoriteResponse(marketplacePlanId=listing_id, isFavorited=True)


@public_router.delete("/listings/{listing_id}/favorite", response_model=FavoriteResponse)
def remove_favorite(
    listing_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> FavoriteResponse:
    service.set_favorite(user, listing_id, is_favorite=False)
    return FavoriteResponse(marketplacePlanId=listing_id, isFavorited=False)


@public_router.get("/me/favorites", response_model=list[ListingSummaryResponse])
def get_user_favorites(
    user: Annotated[User, Depends(require_active_user)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> list[ListingSummaryResponse]:
    return service.get_user_favorites(user)


@public_router.get("/me/plans", response_model=list[BuyerPlanItemResponse])
def get_user_purchased_plans(
    user: Annotated[User, Depends(require_active_user)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> list[BuyerPlanItemResponse]:
    return service.get_buyer_purchased_plans(user)


@public_router.get("/listings/{listing_id}/reviews", response_model=ReviewPaginatedResponse)
def get_listing_reviews(
    listing_id: str,
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50, alias="pageSize"),
) -> ReviewPaginatedResponse:
    return service.get_listing_reviews(listing_id, page=page, page_size=pageSize)


@public_router.post("/listings/{listing_id}/reviews", response_model=ReviewResponse)
def create_or_update_review(
    listing_id: str,
    payload: ReviewCreateRequest,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ReviewResponse:
    return service.create_or_update_review(user, listing_id, payload)


@public_router.post(
    "/listings/{listing_id}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    listing_id: str,
    payload: ReportCreateRequest,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> ReportResponse:
    return service.create_report(user, listing_id, payload)

