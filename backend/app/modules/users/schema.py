from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.preferences.schema import LongTermPreferenceProfile
from app.shared.schemas import ORMBase


class UserRole(StrEnum):
    traveler = "traveler"
    host = "host"
    creator = "creator"
    admin = "admin"


class UserStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    banned = "banned"


class CreatorStatus(StrEnum):
    none = "none"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255, alias="fullName")
    role: UserRole = UserRole.traveler
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    travel_preferences: list[str] = Field(
        default_factory=list, max_length=20, alias="travelPreferences"
    )

    @field_validator("travel_preferences")
    @classmethod
    def normalize_create_preferences(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if any(len(item) > 80 for item in normalized):
            raise ValueError("Each preference must be at most 80 characters")
        return list(dict.fromkeys(normalized))


class UserRead(ORMBase):
    id: int
    email: EmailStr
    full_name: str = Field(alias="fullName")
    role: UserRole
    status: UserStatus
    avatar_url: str | None = Field(alias="avatarUrl")
    bio: str | None
    travel_preferences: list[str] = Field(alias="travelPreferences")
    creator_status: CreatorStatus = Field(alias="creatorStatus")
    creator_portfolio_urls: list[str] = Field(alias="creatorPortfolioUrls")
    created_at: datetime = Field(alias="createdAt")

    @field_validator("travel_preferences", mode="before")
    @classmethod
    def expose_readable_preferences(cls, value: object) -> list[str]:
        return LongTermPreferenceProfile.from_storage(value).top_values()


class ProfileUpdate(BaseModel):
    full_name: Annotated[
        str | None,
        Field(min_length=2, max_length=255, alias="fullName"),
    ] = None
    avatar_url: Annotated[AnyHttpUrl | None, Field(alias="avatarUrl")] = None
    bio: str | None = Field(default=None, max_length=1000)
    travel_preferences: Annotated[
        list[str] | None,
        Field(max_length=20, alias="travelPreferences"),
    ] = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("travel_preferences")
    @classmethod
    def normalize_preferences(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item.strip()]
        if any(len(item) > 80 for item in normalized):
            raise ValueError("Each preference must be at most 80 characters")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def require_change(self) -> "ProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        return self


class CreatorApplicationCreate(BaseModel):
    bio: str = Field(min_length=20, max_length=1000)
    portfolio_urls: list[AnyHttpUrl] = Field(
        default_factory=list,
        max_length=5,
        alias="portfolioUrls",
    )

    model_config = ConfigDict(populate_by_name=True)
