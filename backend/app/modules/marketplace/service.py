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
    Entitlement,
    MarketplacePlan,
    MarketplacePlanVersion,
    Order,
    Report,
    Review,
)
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.marketplace.schema import (
    AdminModerationReviewRequest,
    AuditEventResponse,
    BuyerPlanItemResponse,
    ListingCreateRequest,
    ListingCreatorInfo,
    ListingDetailResponse,
    ListingPaginatedResponse,
    ListingSummaryResponse,
    ListingUpdateRequest,
    ListingVersionResponse,
    PublishablePlanResponse,
    ReportCreateRequest,
    ReportResolveRequest,
    ReportResponse,
    ReviewCreateRequest,
    ReviewPaginatedResponse,
    ReviewResponse,
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

    # Week 5: Buyer Library, Reviews, Reports, Admin Refund & Audit
    def log_audit_event(
        self,
        actor_id: int | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        request_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        clean_meta = {}
        if metadata:
            sensitive = {"password", "token", "jwt", "secret", "cookie", "key"}
            for k, v in metadata.items():
                if any(s in str(k).lower() for s in sensitive):
                    clean_meta[k] = "***REDACTED***"
                else:
                    clean_meta[k] = v
        audit = AuditEvent(
            id=f"evt_{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            metadata_=clean_meta,
        )
        return self.repo.create_audit_event(audit)

    def get_buyer_purchased_plans(self, buyer: User) -> list[BuyerPlanItemResponse]:
        entitlements = self.repo.get_buyer_entitlements(buyer.id)
        results = []
        for ent, plan, ver in entitlements:
            results.append(
                BuyerPlanItemResponse(
                    orderId=ent.order_id,
                    entitlementId=ent.id,
                    marketplacePlanId=plan.id,
                    marketplacePlanVersionId=ver.id,
                    title=ver.title,
                    destination=ver.destination,
                    durationDays=ver.duration_days,
                    copiedPlanId=ent.copied_plan_id,
                    status=ent.status,
                    createdAt=ent.created_at,
                )
            )
        return results

    def create_or_update_review(
        self,
        buyer: User,
        listing_id: str,
        payload: ReviewCreateRequest,
    ) -> ReviewResponse:
        entitlements = self.repo.get_buyer_entitlements(buyer.id)
        matching_ents = [
            (ent, p, v)
            for ent, p, v in entitlements
            if p.id == listing_id
        ]
        if not matching_ents:
            raise AppError(
                403,
                "FORBIDDEN_REVIEW",
                "Bạn cần mua và có quyền truy cập plan này hợp lệ trước khi đánh giá.",
            )

        for ent, p, v in matching_ents:
            order = self.repo.get_order_by_id(ent.order_id)
            if order and order.status == "refunded":
                raise AppError(
                    403,
                    "FORBIDDEN_REVIEW_REFUNDED",
                    "Đơn hàng đã bị hoàn tiền, không thể gửi đánh giá.",
                )

        active_ents = [
            (ent, p, v)
            for ent, p, v in matching_ents
            if ent.status == "active"
        ]
        if not active_ents:
            raise AppError(
                403,
                "FORBIDDEN_REVIEW",
                "Bạn cần mua và có quyền truy cập plan này hợp lệ trước khi đánh giá.",
            )
        ent, p, v = active_ents[0]

        existing = self.repo.get_review_by_user_and_plan(buyer.id, listing_id)
        if existing:
            existing.rating = payload.rating
            existing.comment = payload.comment.strip()
            review = self.repo.create_or_update_review(existing)
        else:
            review = Review(
                id=f"rev_{uuid4().hex[:12]}",
                reviewer_id=buyer.id,
                marketplace_plan_id=listing_id,
                marketplace_plan_version_id=v.id,
                order_id=ent.order_id,
                rating=payload.rating,
                comment=payload.comment.strip(),
                status="published",
            )
            review = self.repo.create_or_update_review(review)

        self.db.commit()
        return ReviewResponse(
            id=review.id,
            reviewerId=review.reviewer_id,
            reviewerName=buyer.full_name,
            reviewerAvatarUrl=buyer.avatar_url,
            marketplacePlanId=review.marketplace_plan_id,
            rating=review.rating,
            comment=review.comment,
            status=review.status,
            createdAt=review.created_at,
            updatedAt=review.updated_at,
        )

    def get_listing_reviews(
        self,
        listing_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> ReviewPaginatedResponse:
        results, total = self.repo.get_reviews_by_listing(listing_id, page, page_size)
        items = [
            ReviewResponse(
                id=r.id,
                reviewerId=r.reviewer_id,
                reviewerName=u.full_name,
                reviewerAvatarUrl=u.avatar_url,
                marketplacePlanId=r.marketplace_plan_id,
                rating=r.rating,
                comment=r.comment,
                status=r.status,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
            for r, u in results
        ]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        return ReviewPaginatedResponse(
            items=items,
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=total_pages,
        )

    def create_report(
        self,
        user: User,
        listing_id: str,
        payload: ReportCreateRequest,
    ) -> ReportResponse:
        plan = self.repo.get_plan_by_id(listing_id)
        if not plan:
            raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing.")

        valid_reasons = {"scam", "outdated", "wrong_info", "inappropriate"}
        if payload.reason not in valid_reasons:
            raise AppError(400, "INVALID_REPORT_REASON", "Lý do báo cáo không hợp lệ.")

        report = Report(
            id=f"rep_{uuid4().hex[:12]}",
            reporter_id=user.id,
            marketplace_plan_id=listing_id,
            marketplace_plan_version_id=plan.current_published_version_id,
            reason=payload.reason,
            description=payload.description.strip(),
            status="pending",
        )
        report = self.repo.create_report(report)
        self.db.commit()

        return ReportResponse(
            id=report.id,
            reporterId=report.reporter_id,
            reporterName=user.full_name,
            marketplacePlanId=report.marketplace_plan_id,
            reason=report.reason,
            description=report.description,
            status=report.status,
            resolution=report.resolution,
            createdAt=report.created_at,
        )

    def get_admin_reports(
        self,
        admin: User,
        status: str | None = None,
        reason: str | None = None,
    ) -> list[ReportResponse]:
        ensure_admin_role(admin.role)
        results = self.repo.get_reports(status=status, reason=reason)
        items = []
        for report, user, plan in results:
            items.append(
                ReportResponse(
                    id=report.id,
                    reporterId=report.reporter_id,
                    reporterName=user.full_name,
                    marketplacePlanId=report.marketplace_plan_id,
                    reason=report.reason,
                    description=report.description,
                    status=report.status,
                    resolution=report.resolution,
                    createdAt=report.created_at,
                )
            )
        return items

    def resolve_report(
        self,
        admin: User,
        report_id: str,
        payload: ReportResolveRequest,
    ) -> ReportResponse:
        ensure_admin_role(admin.role)
        report = self.repo.get_report_by_id(report_id)
        if not report:
            raise AppError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo cáo.")

        if payload.decision not in {"dismiss", "unpublish", "requestChanges"}:
            raise AppError(422, "INVALID_RESOLVE_DECISION", "Quyết định xử lý không hợp lệ.")

        report.status = "resolved" if payload.decision in {"unpublish", "requestChanges"} else "dismissed"
        report.resolution = payload.note or payload.decision

        if payload.decision == "unpublish":
            plan = self.repo.get_plan_by_id(report.marketplace_plan_id)
            if plan:
                plan.status = "unpublished"
                self.repo.update_plan(plan)

        self.log_audit_event(
            actor_id=admin.id,
            action=f"report.{payload.decision}",
            resource_type="report",
            resource_id=report.id,
            metadata={"reason": report.reason, "note": payload.note},
        )
        self.db.commit()

        reporter = UserRepository(self.db).get_by_id(report.reporter_id)
        return ReportResponse(
            id=report.id,
            reporterId=report.reporter_id,
            reporterName=reporter.full_name if reporter else "Unknown",
            marketplacePlanId=report.marketplace_plan_id,
            reason=report.reason,
            description=report.description,
            status=report.status,
            resolution=report.resolution,
            createdAt=report.created_at,
        )

    def admin_refund_order(
        self,
        admin: User,
        order_id: str,
        reason: str | None = None,
    ) -> dict:
        ensure_admin_role(admin.role)
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")

        if order.status == "refunded":
            return {
                "orderId": order.id,
                "status": "refunded",
                "message": "Đơn hàng đã được hoàn tiền trước đó.",
            }

        if order.status != "paid":
            raise AppError(
                400,
                "INVALID_ORDER_STATE",
                "Chỉ có thể hoàn tiền cho đơn hàng đã thanh toán thành công.",
            )

        order.status = "refunded"
        entitlements = self.repo.get_entitlements_by_order_id(order_id)
        for ent in entitlements:
            ent.status = "revoked"
            ent.revoked_at = datetime.now(timezone.utc)
            # Keep copied_plan_id intact per roadmap requirement!

        self.log_audit_event(
            actor_id=admin.id,
            action="order.refund",
            resource_type="order",
            resource_id=order.id,
            metadata={"reason": reason, "amount": order.total_amount},
        )
        self.db.commit()
        return {
            "orderId": order.id,
            "status": "refunded",
            "message": "Hoàn tiền thành công và đã thu hồi quyền truy cập.",
        }

    def get_admin_audit_events(
        self,
        admin: User,
        actor_id: int | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[AuditEventResponse]:
        ensure_admin_role(admin.role)
        events = self.repo.get_audit_events(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return [AuditEventResponse.model_validate(e) for e in events]

