from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.shared.schemas import ORMBase


class UserRole(StrEnum):
    traveler = "traveler"
    host = "host"
    creator = "creator"
    admin = "admin"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Annotated[str, Field(min_length=2, max_length=255, alias="fullName")]
    role: UserRole = UserRole.traveler
    avatar_url: Annotated[str | None, Field(alias="avatarUrl")] = None
    travel_preferences: Annotated[list[str], Field(alias="travelPreferences")] = Field(default_factory=list)


class UserRead(ORMBase):
    id: int
    email: EmailStr
    full_name: Annotated[str, Field(alias="fullName")]
    role: UserRole
    avatar_url: Annotated[str | None, Field(alias="avatarUrl")]
    travel_preferences: Annotated[list[str], Field(alias="travelPreferences")]
    created_at: Annotated[datetime, Field(alias="createdAt")]
