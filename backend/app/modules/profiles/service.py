from uuid import uuid4

from fastapi import status

from app.modules.profiles.model import UserPost, UserVisitedPlace
from app.modules.profiles.repository import ProfileRepository
from app.modules.preferences.repository import TravelerProfileRepository
from app.modules.preferences.schema import (
    TravelerPreferenceSignalRead,
    TravelerProfileRead,
    TravelerProfileUpdate,
)
from app.modules.profiles.schema import (
    ProfileShowcaseRead,
    ExplorePostRead,
    UserPostCreate,
    UserPostRead,
    VisitedPlaceCreate,
    VisitedPlaceRead,
)
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate
from app.shared.errors import AppError


class ProfileService:
    def __init__(
        self,
        users: UserRepository,
        profiles: ProfileRepository,
        traveler_profiles: TravelerProfileRepository,
    ) -> None:
        self.users = users
        self.profiles = profiles
        self.traveler_profiles = traveler_profiles

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

    def create_post(self, user: User, payload: UserPostCreate) -> UserPostRead:
        post = self.profiles.add_post(
            UserPost(
                id=str(uuid4()),
                user_id=user.id,
                content_type=payload.content_type,
                caption=payload.caption,
                media_url=str(payload.media_url),
                location_name=payload.location_name,
            )
        )
        self.profiles.commit()
        return UserPostRead.model_validate(post)

    def normalize_post_text(self, caption: str, location_name: str) -> tuple[str, str]:
        normalized_caption = caption.strip()
        normalized_location = location_name.strip()
        field_errors: dict[str, str] = {}
        if not normalized_caption:
            field_errors["caption"] = "Chú thích không được để trống."
        if not normalized_location:
            field_errors["locationName"] = "Bạn phải gắn địa điểm trước khi đăng."
        if field_errors:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDATION_ERROR",
                "Dữ liệu gửi lên không hợp lệ.",
                field_errors=field_errors,
            )
        return normalized_caption, normalized_location

    def list_public_posts(self, *, limit: int, offset: int) -> list[ExplorePostRead]:
        return [
            ExplorePostRead(
                id=post.id,
                contentType=post.content_type,
                caption=post.caption,
                mediaUrl=post.media_url,
                locationName=post.location_name,
                createdAt=post.created_at,
                authorName=author.full_name,
                authorAvatarUrl=author.avatar_url,
            )
            for post, author in self.profiles.list_public_posts(limit=limit, offset=offset)
        ]

    def update_profile(self, user: User, payload: ProfileUpdate) -> User:
        updated = self.users.update_profile(user, payload)
        if "travel_preferences" in payload.model_fields_set:
            self.traveler_profiles.replace_explicit(
                user.id, payload.travel_preferences or []
            )
        self.users.commit()
        self.users.refresh(updated)
        return updated

    def get_traveler_profile(self, user: User) -> TravelerProfileRead:
        profile = self.traveler_profiles.get(user.id)
        record = self.traveler_profiles.get_record(user.id)
        return TravelerProfileRead(
            userId=user.id,
            explicitPreferences=profile.explicit,
            topPreferences=profile.top_values(),
            observationCount=profile.observation_count,
            updatedAt=profile.updated_at,
            signals=[
                TravelerPreferenceSignalRead(
                    id=signal.id,
                    dimension=signal.dimension,
                    value=signal.value,
                    label=signal.label,
                    score=signal.score,
                    confidence=signal.confidence,
                    observations=signal.observations,
                    scope=signal.scope,
                    destination=signal.destination or None,
                    origin=signal.origin,
                    status=signal.status,
                    sourceTypes=[source.source_type for source in signal.sources],
                    firstObservedAt=signal.first_observed_at,
                    lastObservedAt=signal.last_observed_at,
                    lastEvidenceIntakeId=signal.last_evidence_intake_id,
                )
                for signal in (record.signals if record is not None else [])
            ],
        )

    def update_traveler_profile(
        self, user: User, payload: TravelerProfileUpdate
    ) -> TravelerProfileRead:
        self.traveler_profiles.replace_explicit(
            user.id, payload.explicit_preferences
        )
        self.traveler_profiles.commit()
        return self.get_traveler_profile(user)

    def delete_traveler_profile(self, user: User) -> None:
        self.traveler_profiles.delete(user.id)
        self.traveler_profiles.commit()

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
