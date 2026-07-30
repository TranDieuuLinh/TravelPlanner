from datetime import date, datetime

from pydantic import BaseModel, Field

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
    location_name: str | None = Field(alias="locationName")
    created_at: datetime = Field(alias="createdAt")


class ProfileShowcaseRead(BaseModel):
    model_config = {"populate_by_name": True}

    visited_places: list[VisitedPlaceRead] = Field(alias="visitedPlaces")
    posts: list[UserPostRead]


class VisitedPlaceCreate(BaseModel):
    place_id: str = Field(min_length=1, max_length=36, alias="placeId")
    visited_at: date = Field(alias="visitedAt")
    note: str | None = Field(default=None, max_length=1000)
