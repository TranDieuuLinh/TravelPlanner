from fastapi import status

from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate
from app.shared.errors import AppError


class ProfileService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def update_profile(self, user: User, payload: ProfileUpdate) -> User:
        updated = self.users.update_profile(user, payload)
        self.users.commit()
        self.users.refresh(updated)
        return updated

    def submit_creator_application(self, user: User, payload: CreatorApplicationCreate) -> User:
        if user.role == "admin":
            raise AppError(
                status.HTTP_409_CONFLICT,
                "CREATOR_APPLICATION_NOT_ALLOWED",
                "Tài khoản admin không cần đăng ký creator.",
            )
        if user.role == "creator" or user.creator_status == "verified":
            raise AppError(
                status.HTTP_409_CONFLICT,
                "CREATOR_ALREADY_VERIFIED",
                "Tài khoản đã là creator.",
            )
        if user.creator_status == "pending":
            raise AppError(
                status.HTTP_409_CONFLICT,
                "CREATOR_APPLICATION_PENDING",
                "Yêu cầu creator đang chờ duyệt.",
            )

        updated = self.users.submit_creator_application(user, payload)
        self.users.commit()
        self.users.refresh(updated)
        return updated
