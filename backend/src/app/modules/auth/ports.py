from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class UserRecord:
    id: int
    email: str
    full_name: str
    password_hash: str
    password_salt: str
    role: str
    status: str = "active"
    avatar_url: str | None = None
    bio: str | None = None
    travel_preferences: list[str] | None = None
    creator_status: str = "none"
    creator_portfolio_urls: list[str] | None = None
    created_at: datetime | None = None


@dataclass
class SessionRecord:
    user_id: int
    csrf_token_hash: str
    expires_at: datetime


class UserRepository(Protocol):
    async def by_email(self, email: str) -> UserRecord | None: ...

    async def by_id(self, user_id: int) -> UserRecord | None: ...

    async def create(
        self, email: str, full_name: str, password: str, role: str = "traveler"
    ) -> UserRecord: ...

    async def ensure_user(
        self, email: str, full_name: str, password: str, role: str
    ) -> UserRecord: ...

    async def check_password(self, user: UserRecord, password: str) -> bool: ...

    async def update_user(self, user_id: int, **changes: object) -> UserRecord: ...

    async def create_session(
        self, token_hash: str, user_id: int, csrf_token_hash: str, expires_at: datetime
    ) -> None: ...

    async def session_by_token(self, token_hash: str) -> SessionRecord | None: ...

    async def delete_session(self, token_hash: str) -> None: ...
