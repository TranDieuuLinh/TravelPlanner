from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class PublishablePlanResponse(BaseModel):
    plan_id: str = Field(alias="planId")
    plan_version_id: str = Field(alias="planVersionId")
    owner_id: int = Field(alias="ownerId")
    title: str
    destination: str
    days: int
    status: str
    check_status: str = Field(alias="checkStatus")

    model_config = ConfigDict(populate_by_name=True)


class ListingCreateRequest(BaseModel):
    plan_id: str = Field(alias="planId")
    title: str
    summary: str
    category: str
    price_amount: int = Field(alias="priceAmount")
    currency: str = "VND"
    media_urls: list[str] = Field(default_factory=list, alias="mediaUrls")

    model_config = ConfigDict(populate_by_name=True)


class ListingUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    category: str | None = None
    price_amount: int | None = Field(default=None, alias="priceAmount")
    currency: str | None = None
    media_urls: list[str] | None = Field(default=None, alias="mediaUrls")
    expected_version: int | None = Field(default=None, alias="expectedVersion")

    model_config = ConfigDict(populate_by_name=True)


class ListingVersionResponse(BaseModel):
    id: str
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    version: int
    source_plan_id: str = Field(alias="sourcePlanId")
    source_plan_version_id: str = Field(alias="sourcePlanVersionId")
    title: str
    description: str
    destination: str
    duration_days: int = Field(alias="durationDays")
    category: str
    price_amount: int = Field(alias="priceAmount")
    price_currency: str = Field(alias="priceCurrency")
    media_urls: list[str] = Field(alias="mediaUrls")
    preview_snapshot: dict[str, Any] = Field(alias="previewSnapshot")
    moderation_status: str = Field(alias="moderationStatus")
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    published_at: datetime | None = Field(default=None, alias="publishedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ListingCreatorInfo(BaseModel):
    id: int
    full_name: str = Field(alias="fullName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")

    model_config = ConfigDict(populate_by_name=True)


class ListingDetailResponse(BaseModel):
    id: str
    creator_id: int = Field(alias="creatorId")
    creator: ListingCreatorInfo | None = None
    status: str
    current_published_version_id: str | None = Field(default=None, alias="currentPublishedVersionId")
    current_version: ListingVersionResponse | None = Field(default=None, alias="currentVersion")
    versions: list[ListingVersionResponse] = Field(default_factory=list)
    is_favorited: bool = Field(default=False, alias="isFavorited")
    stats: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ListingSummaryResponse(BaseModel):
    id: str
    creator_id: int = Field(alias="creatorId")
    creator: ListingCreatorInfo | None = None
    status: str
    current_version: ListingVersionResponse = Field(alias="currentVersion")
    is_favorited: bool = Field(default=False, alias="isFavorited")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ListingPaginatedResponse(BaseModel):
    items: list[ListingSummaryResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")

    model_config = ConfigDict(populate_by_name=True)


class FavoriteResponse(BaseModel):
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    is_favorited: bool = Field(alias="isFavorited")

    model_config = ConfigDict(populate_by_name=True)


class AdminModerationReviewRequest(BaseModel):
    decision: str  # "approve" | "reject"
    reason: str | None = None


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str


class ReviewResponse(BaseModel):
    id: str
    reviewer_id: int = Field(alias="reviewerId")
    reviewer_name: str = Field(alias="reviewerName")
    reviewer_avatar_url: str | None = Field(default=None, alias="reviewerAvatarUrl")
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    rating: int
    comment: str
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ReviewPaginatedResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")

    model_config = ConfigDict(populate_by_name=True)


class ReportCreateRequest(BaseModel):
    reason: str  # "scam" | "outdated" | "wrong_info" | "inappropriate"
    description: str


class ReportResponse(BaseModel):
    id: str
    reporter_id: int = Field(alias="reporterId")
    reporter_name: str | None = Field(default=None, alias="reporterName")
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    reason: str
    description: str
    status: str
    resolution: str | None = None
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ReportResolveRequest(BaseModel):
    decision: str  # "dismiss" | "unpublish" | "requestChanges"
    note: str | None = None


class AuditEventResponse(BaseModel):
    id: str
    actor_id: int | None = Field(default=None, alias="actorId")
    action: str
    resource_type: str = Field(alias="resourceType")
    resource_id: str | None = Field(default=None, alias="resourceId")
    request_id: str | None = Field(default=None, alias="requestId")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
    )
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AdminRefundRequest(BaseModel):
    reason: str | None = None
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class BuyerPlanItemResponse(BaseModel):
    order_id: str = Field(alias="orderId")
    entitlement_id: str = Field(alias="entitlementId")
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    marketplace_plan_version_id: str = Field(alias="marketplacePlanVersionId")
    title: str
    destination: str
    duration_days: int = Field(alias="durationDays")
    copied_plan_id: str | None = Field(default=None, alias="copiedPlanId")
    status: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)

