from collections.abc import Sequence

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.travel_groups.model import TravelGroup, TravelGroupMembership, TravelGroupPost
from app.modules.users.model import User


class TravelGroupRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search_public(
        self, *, query: str | None, user_id: int | None
    ) -> Sequence[tuple[TravelGroup, int, bool]]:
        member_count = func.count(TravelGroupMembership.user_id)
        is_member = (
            func.max(case((TravelGroupMembership.user_id == user_id, 1), else_=0))
            if user_id is not None
            else literal(0)
        )
        stmt = (
            select(TravelGroup, member_count.label("member_count"), is_member.label("is_member"))
            .outerjoin(TravelGroupMembership, TravelGroupMembership.group_id == TravelGroup.id)
            .where(TravelGroup.visibility == "public")
            .group_by(TravelGroup.id)
            .order_by(TravelGroup.country_name.asc())
        )
        if query and query.strip():
            needle = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(TravelGroup.country_name.ilike(needle), TravelGroup.name.ilike(needle))
            )
        return self.db.execute(stmt).all()  # type: ignore[return-value]

    def get_public_by_id(self, group_id: int) -> TravelGroup | None:
        return self.db.scalar(
            select(TravelGroup).where(
                TravelGroup.id == group_id, TravelGroup.visibility == "public"
            )
        )

    def get_public_with_membership(
        self, *, group_id: int, user_id: int | None
    ) -> tuple[TravelGroup, int, bool] | None:
        member_count = func.count(TravelGroupMembership.user_id)
        is_member = (
            func.max(case((TravelGroupMembership.user_id == user_id, 1), else_=0))
            if user_id is not None
            else literal(0)
        )
        return self.db.execute(
            select(TravelGroup, member_count.label("member_count"), is_member.label("is_member"))
            .outerjoin(TravelGroupMembership, TravelGroupMembership.group_id == TravelGroup.id)
            .where(TravelGroup.id == group_id, TravelGroup.visibility == "public")
            .group_by(TravelGroup.id)
        ).one_or_none()

    def add_member(self, *, group_id: int, user_id: int) -> bool:
        existing = self.db.scalar(
            select(TravelGroupMembership).where(
                TravelGroupMembership.group_id == group_id,
                TravelGroupMembership.user_id == user_id,
            )
        )
        if existing:
            return False
        self.db.add(TravelGroupMembership(group_id=group_id, user_id=user_id))
        self.db.flush()
        return True

    def member_count(self, group_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(TravelGroupMembership).where(
                    TravelGroupMembership.group_id == group_id
                )
            )
            or 0
        )

    def list_posts(self, group_id: int, *, limit: int = 50) -> list[tuple[TravelGroupPost, User]]:
        return list(
            self.db.execute(
                select(TravelGroupPost, User)
                .join(User, User.id == TravelGroupPost.author_id)
                .where(TravelGroupPost.group_id == group_id)
                .order_by(TravelGroupPost.created_at.desc(), TravelGroupPost.id.desc())
                .limit(limit)
            ).all()
        )

    def post_count(self, group_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(TravelGroupPost).where(
                    TravelGroupPost.group_id == group_id
                )
            )
            or 0
        )

    def add_post(self, post: TravelGroupPost) -> TravelGroupPost:
        self.db.add(post)
        self.db.flush()
        return post
