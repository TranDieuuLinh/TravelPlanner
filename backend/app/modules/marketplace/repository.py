from typing import Sequence

from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.orm import Session

from app.modules.marketplace.model import (
    AuditEvent,
    Favorite,
    MarketplacePlan,
    MarketplacePlanVersion,
)
from app.modules.users.model import User


class MarketplaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_plan(self, plan: MarketplacePlan) -> MarketplacePlan:
        self.db.add(plan)
        self.db.flush()
        return plan

    def update_plan(self, plan: MarketplacePlan) -> MarketplacePlan:
        self.db.flush()
        return plan

    def get_plan_by_id(self, plan_id: str) -> MarketplacePlan | None:
        return self.db.scalar(select(MarketplacePlan).where(MarketplacePlan.id == plan_id))

    def get_plans_by_creator(self, creator_id: int) -> Sequence[MarketplacePlan]:
        return self.db.scalars(
            select(MarketplacePlan)
            .where(MarketplacePlan.creator_id == creator_id)
            .order_by(desc(MarketplacePlan.created_at))
        ).all()

    def create_version(self, version: MarketplacePlanVersion) -> MarketplacePlanVersion:
        self.db.add(version)
        self.db.flush()
        return version

    def update_version(self, version: MarketplacePlanVersion) -> MarketplacePlanVersion:
        self.db.flush()
        return version

    def get_version_by_id(self, version_id: str) -> MarketplacePlanVersion | None:
        return self.db.scalar(select(MarketplacePlanVersion).where(MarketplacePlanVersion.id == version_id))

    def get_versions_by_plan_id(self, plan_id: str) -> Sequence[MarketplacePlanVersion]:
        return self.db.scalars(
            select(MarketplacePlanVersion)
            .where(MarketplacePlanVersion.marketplace_plan_id == plan_id)
            .order_by(desc(MarketplacePlanVersion.version))
        ).all()

    def get_latest_version_for_plan(self, plan_id: str) -> MarketplacePlanVersion | None:
        return self.db.scalar(
            select(MarketplacePlanVersion)
            .where(MarketplacePlanVersion.marketplace_plan_id == plan_id)
            .order_by(desc(MarketplacePlanVersion.version))
            .limit(1)
        )

    def get_current_published_version(self, plan_id: str) -> MarketplacePlanVersion | None:
        plan = self.get_plan_by_id(plan_id)
        if not plan or not plan.current_published_version_id:
            return None
        return self.get_version_by_id(plan.current_published_version_id)

    # Favorite operations
    def add_favorite(self, user_id: int, plan_id: str) -> bool:
        existing = self.db.scalar(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.marketplace_plan_id == plan_id)
        )
        if existing:
            return False
        favorite = Favorite(user_id=user_id, marketplace_plan_id=plan_id)
        self.db.add(favorite)
        self.db.flush()
        return True

    def remove_favorite(self, user_id: int, plan_id: str) -> bool:
        existing = self.db.scalar(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.marketplace_plan_id == plan_id)
        )
        if not existing:
            return False
        self.db.delete(existing)
        self.db.flush()
        return True

    def is_favorited(self, user_id: int, plan_id: str) -> bool:
        fav = self.db.scalar(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.marketplace_plan_id == plan_id)
        )
        return fav is not None

    def get_user_favorite_plan_ids(self, user_id: int) -> list[str]:
        favorites = self.db.scalars(
            select(Favorite.marketplace_plan_id).where(Favorite.user_id == user_id)
        ).all()
        return list(favorites)

    def get_user_favorites(self, user_id: int) -> Sequence[tuple[MarketplacePlan, MarketplacePlanVersion, User]]:
        query = (
            select(MarketplacePlan, MarketplacePlanVersion, User)
            .join(Favorite, Favorite.marketplace_plan_id == MarketplacePlan.id)
            .join(
                MarketplacePlanVersion,
                MarketplacePlanVersion.id == MarketplacePlan.current_published_version_id,
            )
            .join(User, User.id == MarketplacePlan.creator_id)
            .where(
                Favorite.user_id == user_id,
                MarketplacePlan.status == "published",
            )
            .order_by(desc(Favorite.created_at))
        )
        return self.db.execute(query).all()  # type: ignore

    # Public Search
    def search_published_listings(
        self,
        page: int = 1,
        page_size: int = 12,
        query: str | None = None,
        category: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        sort: str = "newest",
    ) -> tuple[Sequence[tuple[MarketplacePlan, MarketplacePlanVersion, User]], int]:
        stmt = (
            select(MarketplacePlan, MarketplacePlanVersion, User)
            .join(
                MarketplacePlanVersion,
                MarketplacePlanVersion.id == MarketplacePlan.current_published_version_id,
            )
            .join(User, User.id == MarketplacePlan.creator_id)
            .where(MarketplacePlan.status == "published")
        )

        if query and query.strip():
            needle = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    MarketplacePlanVersion.title.ilike(needle),
                    MarketplacePlanVersion.description.ilike(needle),
                    MarketplacePlanVersion.destination.ilike(needle),
                    User.full_name.ilike(needle),
                )
            )

        if category and category.strip() and category.strip() != "Tất cả":
            stmt = stmt.where(func.lower(MarketplacePlanVersion.category) == category.strip().lower())

        if min_price is not None:
            stmt = stmt.where(MarketplacePlanVersion.price_amount >= min_price)

        if max_price is not None:
            stmt = stmt.where(MarketplacePlanVersion.price_amount <= max_price)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Sorting
        if sort == "priceAsc":
            stmt = stmt.order_by(asc(MarketplacePlanVersion.price_amount))
        elif sort == "priceDesc":
            stmt = stmt.order_by(desc(MarketplacePlanVersion.price_amount))
        else:  # newest or rating (fallback to newest)
            stmt = stmt.order_by(desc(MarketplacePlanVersion.published_at), desc(MarketplacePlanVersion.created_at))

        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        results = self.db.execute(stmt).all()
        return results, total  # type: ignore

    # Admin Moderation
    def get_pending_listing_versions(self) -> Sequence[tuple[MarketplacePlanVersion, MarketplacePlan, User]]:
        stmt = (
            select(MarketplacePlanVersion, MarketplacePlan, User)
            .join(MarketplacePlan, MarketplacePlan.id == MarketplacePlanVersion.marketplace_plan_id)
            .join(User, User.id == MarketplacePlan.creator_id)
            .where(MarketplacePlanVersion.moderation_status == "pending_review")
            .order_by(asc(MarketplacePlanVersion.updated_at))
        )
        return self.db.execute(stmt).all()  # type: ignore

    # Audit Events
    def create_audit_event(self, event: AuditEvent) -> AuditEvent:
        self.db.add(event)
        self.db.flush()
        return event
