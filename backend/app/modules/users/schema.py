from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, EmailStr, Field

from app.shared.schemas import ORMBase


class UserRole(StrEnum):
    traveler = "traveler"
    host = "host"
    creator = "creator"
    admin = "admin"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255, alias="fullName")
    role: UserRole = UserRole.traveler
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    travel_preferences: list[str] = Field(default_factory=list, alias="travelPreferences")


class UserRead(ORMBase):
    id: int
    email: EmailStr
    full_name: str = Field(alias="fullName")
    role: UserRole
    avatar_url: str | None = Field(alias="avatarUrl")
    travel_preferences: list[str] = Field(alias="travelPreferences")
    created_at: datetime = Field(alias="createdAt")
