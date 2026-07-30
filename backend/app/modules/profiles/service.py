from uuid import uuid4

from fastapi import status

from app.modules.profiles.model import UserVisitedPlace
from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schema import (
    ProfileShowcaseRead,
    UserPostRead,
    VisitedPlaceCreate,
    VisitedPlaceRead,
)
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate
from app.shared.errors import AppError


class ProfileService:
    def __init__(self, users: UserRepository, profiles: ProfileRepository) -> None:
        self.users = users
        self.profiles = profiles

    def get_showcase(self, user: User) -> ProfileShowcaseRead:
        visited_places = [
            VisitedPlaceRead(
                id=visited.id,
                placeId=place.id,
                name=place.name,
                address=place.address,
                city=place.city,
                country=place.country,
                latitude=float(place.latitude),
                longitude=float(place.longitude),
                visitedAt=visited.visited_at,
                note=visited.note,
            )
            for visited, place in self.profiles.list_visited_places(user.id)
        ]
        posts = [UserPostRead.model_validate(post) for post in self.profiles.list_posts(user.id)]
        return ProfileShowcaseRead(visitedPlaces=visited_places, posts=posts)

    def mark_place_visited(self, user: User, payload: VisitedPlaceCreate) -> VisitedPlaceRead:
        place = self.profiles.get_place(payload.place_id)
        if not place or place.deleted_at is not None:
            raise AppError(status.HTTP_404_NOT_FOUND, "PLACE_NOT_FOUND", "Không tìm thấy địa điểm.")
        if place.latitude is None or place.longitude is None:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "PLACE_COORDINATES_REQUIRED",
                "Địa điểm cần có tọa độ trước khi đánh dấu trên bản đồ.",
            )

        visited = self.profiles.get_visited_place(user.id, place.id)
        if visited:
            visited.visited_at = payload.visited_at
            visited.note = payload.note
        else:
            visited = self.profiles.add_visited_place(
                UserVisitedPlace(
                    id=str(uuid4()),
                    user_id=user.id,
                    place_id=place.id,
                    visited_at=payload.visited_at,
                    note=payload.note,
                )
            )
        self.profiles.commit()
        return VisitedPlaceRead(
            id=visited.id,
            placeId=place.id,
            name=place.name,
            address=place.address,
            city=place.city,
            country=place.country,
            latitude=float(place.latitude),
            longitude=float(place.longitude),
            visitedAt=visited.visited_at,
            note=visited.note,
        )

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
