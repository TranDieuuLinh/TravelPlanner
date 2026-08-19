from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AuthModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuthUser(AuthModel):
    id: int
    email: str
    full_name: str
    role: str
    status: str
    avatar_url: str | None = None
    bio: str | None = None
    travel_preferences: list[str] = Field(default_factory=list)
    creator_status: str = "none"
    creator_portfolio_urls: list[str] = Field(default_factory=list)
    created_at: datetime


class LoginInput(AuthModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RegisterInput(AuthModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(AuthModel):
    user: AuthUser
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class RefreshInput(AuthModel):
    refresh_token: str | None = None


class ProfileUpdateInput(AuthModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    avatar_url: str | None = None
    bio: str | None = Field(default=None, max_length=4000)
    travel_preferences: list[str] | None = None


class CreatorApplicationInput(AuthModel):
    bio: str = Field(min_length=1, max_length=4000)
    portfolio_urls: list[str] = Field(default_factory=list, max_length=20)
