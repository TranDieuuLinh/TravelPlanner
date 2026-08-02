from datetime import date, datetime

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.shared.schemas import ORMBase


class VisitedPlaceRead(ORMBase):
    id: str
    place_id: str = Field(alias="placeId")
    name: str
    address: str | None
    city: str | None
    country: str | None
    latitude: float
    longitude: float
    visited_at: date = Field(alias="visitedAt")
    note: str | None


class UserPostRead(ORMBase):
    id: str
    caption: str
    media_url: str = Field(alias="mediaUrl")
    content_type: Literal["post", "reel"] = Field(alias="contentType")
    location_name: str = Field(alias="locationName")
    created_at: datetime = Field(alias="createdAt")


class UserPostCreate(BaseModel):
    model_config = {"populate_by_name": True}

    content_type: Literal["post", "reel"] = Field(alias="contentType")
    caption: str = Field(min_length=1, max_length=2200)
    media_url: AnyHttpUrl = Field(alias="mediaUrl")
    location_name: str = Field(min_length=1, max_length=255, alias="locationName")

    @field_validator("caption", "location_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Trường này không được để trống.")
        return normalized


class ExplorePostRead(UserPostRead):
    author_name: str = Field(alias="authorName")
    author_avatar_url: str | None = Field(alias="authorAvatarUrl")


class ProfileShowcaseRead(BaseModel):
    model_config = {"populate_by_name": True}

    visited_places: list[VisitedPlaceRead] = Field(alias="visitedPlaces")
    posts: list[UserPostRead]


class VisitedPlaceCreate(BaseModel):
    place_id: str = Field(min_length=1, max_length=36, alias="placeId")
    visited_at: date = Field(alias="visitedAt")
    note: str | None = Field(default=None, max_length=1000)
