from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.marketplace.domain.rules import (
    ensure_admin_role,
    ensure_creator_role,
    ensure_listing_ownership,
    ensure_publishable_status,
    validate_submittable_version,
)
from app.modules.marketplace.model import (
    AuditEvent,
    MarketplacePlan,
    MarketplacePlanVersion,
)
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.marketplace.schema import (
    AdminModerationReviewRequest,
    ListingCreateRequest,
    ListingCreatorInfo,
    ListingDetailResponse,
    ListingPaginatedResponse,
    ListingSummaryResponse,
    ListingUpdateRequest,
    ListingVersionResponse,
    PublishablePlanResponse,
)
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.contracts.plan_marketplace import PlanMarketplaceGateway
from app.shared.errors import AppError


class MarketplaceService:
    def __init__(
        self,
        db: Session,
        repo: MarketplaceRepository,
        plan_gateway: PlanMarketplaceGateway,
    ) -> None:
        self.db = db
        self.repo = repo
        self.plan_gateway = plan_gateway

    def list_publishable_plans(self, user: User) -> list[PublishablePlanResponse]:
        ensure_creator_role(user.role)
        plans = self.plan_gateway.list_publishable_plans(user.id)
        return [
            PublishablePlanResponse(
                planId=p.plan_id,
                planVersionId=p.plan_version_id,
                ownerId=p.owner_id,
                title=p.title,
                destination=p.destination,
                days=p.days,
                status=p.status,
                checkStatus=p.check_status,
            )
            for p in plans
        ]

    def create_listing(self, user: User, payload: ListingCreateRequest) -> ListingDetailResponse:
        ensure_creator_role(user.role)

        publish_info = self.plan_gateway.get_publish_info(payload.plan_id, user.id)
        if publish_info.owner_id != user.id:
            raise AppError(403, "NOT_PLAN_OWNER", "Bạn không phải là chủ sở hữu của plan này.")

        preview = self.plan_gateway.get_preview(publish_info.plan_version_id)

        plan_id = f"mp_{uuid4().hex[:12]}"
        version_id = f"mpv_{uuid4().hex[:12]}"

        plan = MarketplacePlan(
            id=plan_id,
            creator_id=user.id,
            status="draft",
            current_published_version_id=None,
        )
        self.repo.create_plan(plan)

        version = MarketplacePlanVersion(
            id=version_id,
            marketplace_plan_id=plan.id,
            version=1,
            source_plan_id=payload.plan_id,
            source_plan_version_id=publish_info.plan_version_id,
            title=payload.title,
            description=payload.summary,
            destination=publish_info.destination,
            duration_days=publish_info.days,
            category=payload.category,
            price_amount=payload.price_amount,
            price_currency=payload.currency,
            media_urls=payload.media_urls,
            preview_snapshot=preview.model_dump(by_alias=True),
            moderation_status="draft",
        )
        self.repo.create_version(version)
        self.db.commit()

        return self._build_detail_response(plan, [version], user, is_favorited=False)

    def get_creator_listings(self, user: User) -> list[ListingDetailResponse]:
        ensure_creator_role(user.role)
        plans = self.repo.get_plans_by_creator(user.id)
        responses = []
        for plan in plans:
            versions = self.repo.get_versions_by_plan_id(plan.id)
            responses.append(self._build_detail_response(plan, versions, user, is_favorited=False))
        return responses

    def get_creator_listing_detail(self, user: User, listing_id: str) -> ListingDetailResponse:
        ensure_creator_role(user.role)
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")
        ensure_listing_ownership(plan.creator_id, user.id)

        versions = self.repo.get_versions_by_plan_id(plan.id)
        return self._build_detail_response(plan, versions, user, is_favorited=False)

    def update_listing(self, user: User, listing_id: str, payload: ListingUpdateRequest) -> ListingDetailResponse:
        ensure_creator_role(user.role)
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")
        ensure_listing_ownership(plan.creator_id, user.id)

        latest_version = self.repo.get_latest_version_for_plan(plan.id)
        if not latest_version:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản của listing.")

        if payload.expected_version is not None and latest_version.version != payload.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Dữ liệu listing đã được cập nhật ở nơi khác.")

        # Check if latest version is published or approved - if so, create a new draft version
        if latest_version.moderation_status in ("published", "approved") or plan.status == "published":
            new_version_num = latest_version.version + 1
            new_version_id = f"mpv_{uuid4().hex[:12]}"
            target_version = MarketplacePlanVersion(
                id=new_version_id,
                marketplace_plan_id=plan.id,
                version=new_version_num,
                source_plan_id=latest_version.source_plan_id,
                source_plan_version_id=latest_version.source_plan_version_id,
                title=payload.title if payload.title is not None else latest_version.title,
                description=payload.summary if payload.summary is not None else latest_version.description,
                destination=latest_version.destination,
                duration_days=latest_version.duration_days,
                category=payload.category if payload.category is not None else latest_version.category,
                price_amount=payload.price_amount if payload.price_amount is not None else latest_version.price_amount,
                price_currency=payload.currency if payload.currency is not None else latest_version.price_currency,
                media_urls=payload.media_urls if payload.media_urls is not None else latest_version.media_urls,
                preview_snapshot=latest_version.preview_snapshot,
                moderation_status="draft",
                rejection_reason=None,
            )
            self.repo.create_version(target_version)
        else:
            # Update existing draft/pending/rejected version
            if payload.title is not None:
                latest_version.title = payload.title
            if payload.summary is not None:
                latest_version.description = payload.summary
            if payload.category is not None:
                latest_version.category = payload.category
            if payload.price_amount is not None:
                latest_version.price_amount = payload.price_amount
            if payload.currency is not None:
                latest_version.price_currency = payload.currency
            if payload.media_urls is not None:
                latest_version.media_urls = payload.media_urls

            latest_version.moderation_status = "draft"
            latest_version.rejection_reason = None
            self.repo.update_version(latest_version)

        self.db.commit()
        versions = self.repo.get_versions_by_plan_id(plan.id)
        return self._build_detail_response(plan, versions, user, is_favorited=False)

    def submit_listing(self, user: User, listing_id: str) -> ListingDetailResponse:
        ensure_creator_role(user.role)
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")
        ensure_listing_ownership(plan.creator_id, user.id)

        latest_version = self.repo.get_latest_version_for_plan(plan.id)
        if not latest_version:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản.")

        publish_info = self.plan_gateway.get_publish_info(latest_version.source_plan_id, user.id)

        validate_submittable_version(
            title=latest_version.title,
            description=latest_version.description,
            category=latest_version.category,
            price_amount=latest_version.price_amount,
            media_urls=latest_version.media_urls,
            preview_snapshot=latest_version.preview_snapshot,
            check_status=publish_info.check_status,
            plan_status=publish_info.status,
        )

        latest_version.moderation_status = "pending_review"
        latest_version.rejection_reason = None
        self.repo.update_version(latest_version)
        self.db.commit()

        versions = self.repo.get_versions_by_plan_id(plan.id)
        return self._build_detail_response(plan, versions, user, is_favorited=False)

    def publish_listing(self, user: User, listing_id: str) -> ListingDetailResponse:
        ensure_creator_role(user.role)
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")
        ensure_listing_ownership(plan.creator_id, user.id)

        latest_version = self.repo.get_latest_version_for_plan(plan.id)
        if not latest_version:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản.")

        ensure_publishable_status(latest_version.moderation_status)

        now = datetime.now(timezone.utc)
        latest_version.moderation_status = "published"
        latest_version.published_at = now
        self.repo.update_version(latest_version)

        plan.current_published_version_id = latest_version.id
        plan.status = "published"
        self.repo.update_plan(plan)

        audit = AuditEvent(
            id=f"evt_{uuid4().hex[:12]}",
            actor_id=user.id,
            action="listing.publish",
            resource_type="marketplace_plan",
            resource_id=plan.id,
            metadata_={"version_id": latest_version.id, "version": latest_version.version},
        )
        self.repo.create_audit_event(audit)

        self.db.commit()

        versions = self.repo.get_versions_by_plan_id(plan.id)
        return self._build_detail_response(plan, versions, user, is_favorited=False)

    def unpublish_listing(self, user: User, listing_id: str) -> ListingDetailResponse:
        ensure_creator_role(user.role)
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")
        ensure_listing_ownership(plan.creator_id, user.id)

        plan.status = "unpublished"
        self.repo.update_plan(plan)

        audit = AuditEvent(
            id=f"evt_{uuid4().hex[:12]}",
            actor_id=user.id,
            action="listing.unpublish",
            resource_type="marketplace_plan",
            resource_id=plan.id,
            metadata_={},
        )
        self.repo.create_audit_event(audit)

        self.db.commit()

        versions = self.repo.get_versions_by_plan_id(plan.id)
        return self._build_detail_response(plan, versions, user, is_favorited=False)

    # Public Methods
    def search_public_listings(
        self,
        user: User | None,
        page: int = 1,
        page_size: int = 12,
        query: str | None = None,
        category: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        sort: str = "newest",
    ) -> ListingPaginatedResponse:
        results, total = self.repo.search_published_listings(
            page=page,
            page_size=page_size,
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
        )

        user_fav_ids = set(self.repo.get_user_favorite_plan_ids(user.id)) if user else set()

        items = []
        for plan, version, creator in results:
            creator_info = ListingCreatorInfo(
                id=creator.id,
                fullName=creator.full_name,
                avatarUrl=creator.avatar_url,
            )
            version_resp = ListingVersionResponse.model_validate(version)
            items.append(
                ListingSummaryResponse(
                    id=plan.id,
                    creatorId=plan.creator_id,
                    creator=creator_info,
                    status=plan.status,
                    currentVersion=version_resp,
                    isFavorited=plan.id in user_fav_ids,
                    createdAt=plan.created_at,
                )
            )

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        return ListingPaginatedResponse(
            items=items,
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=total_pages,
        )

    def get_public_listing_detail(self, user: User | None, listing_id: str) -> ListingDetailResponse:
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan or plan.status != "published":
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing hoặc listing đã bị ẩn.")

        published_version = self.repo.get_current_published_version(plan.id)
        if not published_version:
            raise AppError(404, "VERSION_NOT_FOUND", "Listing chưa có phiên bản phát hành.")

        creator = UserRepository(self.db).get_by_id(plan.creator_id)
        is_fav = self.repo.is_favorited(user.id, plan.id) if user else False

        return self._build_detail_response(plan, [published_version], creator, is_favorited=is_fav)

    def set_favorite(self, user: User, listing_id: str, is_favorite: bool) -> bool:
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")

        if is_favorite:
            result = self.repo.add_favorite(user.id, listing_id)
        else:
            result = self.repo.remove_favorite(user.id, listing_id)

        self.db.commit()
        return result

    def get_user_favorites(self, user: User) -> list[ListingSummaryResponse]:
        fav_results = self.repo.get_user_favorites(user.id)
        items = []
        for plan, version, creator in fav_results:
            creator_info = ListingCreatorInfo(
                id=creator.id,
                fullName=creator.full_name,
                avatarUrl=creator.avatar_url,
            )
            version_resp = ListingVersionResponse.model_validate(version)
            items.append(
                ListingSummaryResponse(
                    id=plan.id,
                    creatorId=plan.creator_id,
                    creator=creator_info,
                    status=plan.status,
                    currentVersion=version_resp,
                    isFavorited=True,
                    createdAt=plan.created_at,
                )
            )
        return items

    # Admin Methods
    def get_admin_pending_listings(self, admin: User) -> list[dict]:
        ensure_admin_role(admin.role)
        records = self.repo.get_pending_listing_versions()
        items = []
        for version, plan, creator in records:
            items.append(
                {
                    "listingVersionId": version.id,
                    "listingId": plan.id,
                    "version": version.version,
                    "title": version.title,
                    "description": version.description,
                    "destination": version.destination,
                    "durationDays": version.duration_days,
                    "category": version.category,
                    "priceAmount": version.price_amount,
                    "priceCurrency": version.price_currency,
                    "mediaUrls": version.media_urls,
                    "previewSnapshot": version.preview_snapshot,
                    "creator": {
                        "id": creator.id,
                        "fullName": creator.full_name,
                        "avatarUrl": creator.avatar_url,
                    },
                    "createdAt": version.created_at.isoformat(),
                    "updatedAt": version.updated_at.isoformat(),
                }
            )
        return items

    def review_listing_version(
        self,
        admin: User,
        version_id: str,
        payload: AdminModerationReviewRequest,
    ) -> ListingVersionResponse:
        ensure_admin_role(admin.role)
        version = self.repo.get_version_by_id(version_id)
        if not version:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản listing cần duyệt.")

        if version.moderation_status != "pending_review":
            raise AppError(400, "INVALID_MODERATION_STATE", f"Phiên bản không ở trạng thái chờ duyệt (hiện tại: {version.moderation_status}).")

        if payload.decision == "approve":
            version.moderation_status = "approved"
            version.rejection_reason = None
        elif payload.decision == "reject":
            version.moderation_status = "rejected"
            version.rejection_reason = payload.reason or "Nội dung chưa đạt yêu cầu kiểm duyệt."
        else:
            raise AppError(422, "INVALID_DECISION", "Quyết định duyệt phải là approve hoặc reject.")

        self.repo.update_version(version)

        audit = AuditEvent(
            id=f"evt_{uuid4().hex[:12]}",
            actor_id=admin.id,
            action=f"listing_version.{payload.decision}",
            resource_type="marketplace_plan_version",
            resource_id=version.id,
            metadata_={"decision": payload.decision, "reason": payload.reason},
        )
        self.repo.create_audit_event(audit)

        self.db.commit()
        return ListingVersionResponse.model_validate(version)

    # Helpers
    def _build_detail_response(
        self,
        plan: MarketplacePlan,
        versions: Sequence[MarketplacePlanVersion],
        creator: User | None,
        is_favorited: bool = False,
    ) -> ListingDetailResponse:
        creator_info = (
            ListingCreatorInfo(id=creator.id, fullName=creator.full_name, avatarUrl=creator.avatar_url)
            if creator
            else None
        )

        version_responses = [ListingVersionResponse.model_validate(v) for v in versions]

        current_ver_resp = None
        if plan.current_published_version_id:
            for vr in version_responses:
                if vr.id == plan.current_published_version_id:
                    current_ver_resp = vr
                    break
        if not current_ver_resp and version_responses:
            current_ver_resp = version_responses[0]

        return ListingDetailResponse(
            id=plan.id,
            creatorId=plan.creator_id,
            creator=creator_info,
            status=plan.status,
            currentPublishedVersionId=plan.current_published_version_id,
            currentVersion=current_ver_resp,
            versions=version_responses,
            isFavorited=is_favorited,
            stats={"views": 0, "orders": 0, "grossRevenue": 0},
            createdAt=plan.created_at,
            updatedAt=plan.updated_at,
        )
