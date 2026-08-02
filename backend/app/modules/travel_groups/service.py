from sqlalchemy.orm import Session
from uuid import uuid4

from app.modules.travel_groups.model import TravelGroupPost
from app.modules.travel_groups.repository import TravelGroupRepository
from app.modules.travel_groups.schema import (
    TravelGroupDetailResponse,
    TravelGroupListResponse,
    TravelGroupMembershipResponse,
    TravelGroupPostAuthorResponse,
    TravelGroupPostCreate,
    TravelGroupPostResponse,
    TravelGroupResponse,
)
from app.modules.users.model import User
from app.shared.errors import AppError


class TravelGroupService:
    def __init__(self, db: Session, repository: TravelGroupRepository) -> None:
        self.db = db
        self.repository = repository

    def search(self, *, query: str | None, user: User | None) -> TravelGroupListResponse:
        rows = self.repository.search_public(query=query, user_id=user.id if user else None)
        items = [
            TravelGroupResponse(
                id=group.id,
                countryCode=group.country_code,
                countryName=group.country_name,
                name=group.name,
                photoUrl=group.photo_url,
                memberCount=member_count,
                isMember=bool(is_member),
                isPublic=group.visibility == "public",
            )
            for group, member_count, is_member in rows
        ]
        return TravelGroupListResponse(items=items, total=len(items))

    @staticmethod
    def _group_response(group, member_count: int, is_member: bool) -> TravelGroupResponse:
        return TravelGroupResponse(
            id=group.id,
            countryCode=group.country_code,
            countryName=group.country_name,
            name=group.name,
            photoUrl=group.photo_url,
            memberCount=member_count,
            isMember=bool(is_member),
            isPublic=group.visibility == "public",
        )

    @staticmethod
    def _post_response(post: TravelGroupPost, author: User) -> TravelGroupPostResponse:
        return TravelGroupPostResponse(
            id=post.id,
            content=post.content,
            createdAt=post.created_at,
            author=TravelGroupPostAuthorResponse(
                id=author.id,
                fullName=author.full_name,
                avatarUrl=author.avatar_url,
            ),
        )

    def detail(self, *, group_id: int, user: User | None) -> TravelGroupDetailResponse:
        row = self.repository.get_public_with_membership(
            group_id=group_id, user_id=user.id if user else None
        )
        if not row:
            raise AppError(404, "TRAVEL_GROUP_NOT_FOUND", "Không tìm thấy nhóm du lịch.")
        group, member_count, is_member = row
        posts = [self._post_response(post, author) for post, author in self.repository.list_posts(group_id)]
        return TravelGroupDetailResponse(
            group=self._group_response(group, member_count, bool(is_member)),
            posts=posts,
            totalPosts=self.repository.post_count(group_id),
        )

    def create_post(
        self, *, group_id: int, user: User, payload: TravelGroupPostCreate
    ) -> TravelGroupPostResponse:
        if not self.repository.get_public_by_id(group_id):
            raise AppError(404, "TRAVEL_GROUP_NOT_FOUND", "Không tìm thấy nhóm du lịch.")
        content = payload.content.strip()
        if not content:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Bài viết cần có nội dung.",
                field_errors={"content": "Bài viết cần có nội dung."},
            )
        post = self.repository.add_post(
            TravelGroupPost(
                id=str(uuid4()), group_id=group_id, author_id=user.id, content=content
            )
        )
        self.db.commit()
        self.db.refresh(post)
        return self._post_response(post, user)

    def join(self, *, group_id: int, user: User) -> TravelGroupMembershipResponse:
        if not self.repository.get_public_by_id(group_id):
            raise AppError(404, "TRAVEL_GROUP_NOT_FOUND", "Không tìm thấy nhóm du lịch.")
        self.repository.add_member(group_id=group_id, user_id=user.id)
        self.db.commit()
        return TravelGroupMembershipResponse(
            groupId=group_id,
            isMember=True,
            memberCount=self.repository.member_count(group_id),
        )
