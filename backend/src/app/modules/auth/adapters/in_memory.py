from datetime import datetime, timezone

from app.modules.auth.ports import SessionRecord, UserRecord
from app.modules.auth.security import new_password, token_digest, verify_password


class InMemoryUserRepository:
    """Fallback provider for tests and development without DATABASE_URL."""

    def __init__(self) -> None:
        self._users: dict[int, UserRecord] = {}
        self._by_email: dict[str, int] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._next_id = 1

    async def by_email(self, email: str) -> UserRecord | None:
        user_id = self._by_email.get(email.lower())
        return self._users.get(user_id) if user_id else None

    async def by_id(self, user_id: int) -> UserRecord | None:
        return self._users.get(user_id)

    async def create(
        self, email: str, full_name: str, password: str, role: str = "traveler"
    ) -> UserRecord:
        password_digest, password_salt = new_password(password)
        user = UserRecord(
            id=self._next_id,
            email=email.lower(),
            full_name=full_name,
            password_hash=password_digest,
            password_salt=password_salt,
            role=role,
            travel_preferences=[],
            creator_portfolio_urls=[],
            created_at=datetime.now(timezone.utc),
        )
        self._users[user.id] = user
        self._by_email[user.email] = user.id
        self._next_id += 1
        return user

    async def ensure_user(
        self, email: str, full_name: str, password: str, role: str
    ) -> UserRecord:
        existing = await self.by_email(email)
        return existing or await self.create(email, full_name, password, role)

    async def check_password(self, user: UserRecord, password: str) -> bool:
        return verify_password(password, user.password_hash, user.password_salt)

    async def update_user(self, user_id: int, **changes: object) -> UserRecord:
        user = self._users[user_id]
        for key, value in changes.items():
            if value is not None and hasattr(user, key):
                setattr(user, key, value)
        return user

    async def create_session(
        self, token_hash: str, user_id: int, csrf_token_hash: str, expires_at: datetime
    ) -> None:
        self._sessions[token_hash] = SessionRecord(user_id, csrf_token_hash, expires_at)

    async def session_by_token(self, token_hash: str) -> SessionRecord | None:
        session = self._sessions.get(token_hash)
        if session and session.expires_at > datetime.now(timezone.utc):
            return session
        if session:
            self._sessions.pop(token_hash, None)
        return None

    async def delete_session(self, token_hash: str) -> None:
        self._sessions.pop(token_hash, None)
