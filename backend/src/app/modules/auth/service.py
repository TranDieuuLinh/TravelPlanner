import asyncio
import re
import secrets
from datetime import datetime, timedelta, timezone

import asyncpg

from app.modules.auth.contract import AuthUser
from app.modules.auth.errors import AuthError
from app.modules.auth.ports import SessionRecord, UserRecord, UserRepository
from app.modules.auth.security import token_digest


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthService:
    session_ttl = timedelta(days=7)

    def __init__(
        self,
        repository: UserRepository,
        bootstrap_users: list[tuple[str, str, str, str]] | None = None,
    ) -> None:
        self.repository = repository
        self.bootstrap_users = bootstrap_users or []
        self._ready = False

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        for email, full_name, password, role in self.bootstrap_users:
            await self.repository.ensure_user(email, full_name, password, role)
        self._ready = True

    async def user(self, token: str | None) -> AuthUser | None:
        await self.ensure_ready()
        session = await self._session(token)
        if not session:
            return None
        return self._to_user(await self.repository.by_id(session.user_id))

    async def authorize(
        self, token: str | None, csrf_token: str | None = None, *, require_csrf: bool = False
    ) -> AuthUser:
        """Resolve a session for feature modules without exposing session internals."""
        await self.ensure_ready()
        session = await self._require_session(token)
        if require_csrf:
            self._require_csrf(session, csrf_token)
        return self._to_user(await self.repository.by_id(session.user_id))

    async def login(self, email: str, password: str) -> tuple[AuthUser, str, str]:
        await self.ensure_ready()
        record = await self.repository.by_email(email.strip().lower())
        if not record or not await self.repository.check_password(record, password):
            raise AuthError(
                "Email hoặc mật khẩu không đúng.",
                status_code=401,
                code="INVALID_CREDENTIALS",
            )
        return await self._start_session(record)

    async def register(
        self, full_name: str, email: str, password: str
    ) -> tuple[AuthUser, str, str]:
        await self.ensure_ready()
        normalized_email = email.strip().lower()
        self._validate_registration(full_name, normalized_email, password)
        if await self.repository.by_email(normalized_email):
            raise AuthError(
                "Email này đã được đăng ký.",
                status_code=409,
                code="EMAIL_ALREADY_EXISTS",
                field_errors={"email": "Email này đã được đăng ký."},
            )
        try:
            record = await self.repository.create(normalized_email, full_name.strip(), password)
        except Exception as error:
            if "unique" in str(error).lower() or "duplicate" in str(error).lower():
                raise AuthError(
                    "Email này đã được đăng ký.",
                    status_code=409,
                    code="EMAIL_ALREADY_EXISTS",
                ) from error
            raise
        return await self._start_session(record)

    async def refresh(
        self, token: str | None, csrf_token: str | None
    ) -> tuple[AuthUser, str, str]:
        session = await self._require_session(token)
        self._require_csrf(session, csrf_token)
        record = await self.repository.by_id(session.user_id)
        if not record:
            raise AuthError(
                "Phiên đăng nhập không còn hợp lệ.",
                status_code=401,
                code="UNAUTHENTICATED",
            )
        await self.repository.delete_session(token_digest(token or ""))
        return await self._start_session(record)

    async def logout(self, token: str | None, csrf_token: str | None) -> None:
        session = await self._session(token)
        if session:
            self._require_csrf(session, csrf_token)
            await self.repository.delete_session(token_digest(token or ""))

    async def update_profile(
        self, token: str | None, csrf_token: str | None, **changes: object
    ) -> AuthUser:
        session = await self._require_session(token)
        self._require_csrf(session, csrf_token)
        record = await self.repository.update_user(session.user_id, **changes)
        return self._to_user(record)

    async def _start_session(self, record: UserRecord) -> tuple[AuthUser, str, str]:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        await self.repository.create_session(
            token_digest(token),
            record.id,
            token_digest(csrf_token),
            datetime.now(timezone.utc) + self.session_ttl,
        )
        return self._to_user(record), token, csrf_token

    async def _session(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None

        # Aiven/cloud PostgreSQL may close an idle connection between requests.
        # Retry only connection-level failures; authentication/SQL errors must
        # still surface normally instead of being hidden.
        for attempt in range(2):
            try:
                return await self.repository.session_by_token(token_digest(token))
            except (asyncpg.PostgresConnectionError, ConnectionError):
                if attempt == 1:
                    raise
                await asyncio.sleep(0.2)
        return None

    async def _require_session(self, token: str | None) -> SessionRecord:
        session = await self._session(token)
        if not session:
            raise AuthError("Chưa đăng nhập.", status_code=401, code="UNAUTHENTICATED")
        return session

    @staticmethod
    def _require_csrf(session: SessionRecord, csrf_token: str | None) -> None:
        if not csrf_token or not secrets.compare_digest(
            session.csrf_token_hash, token_digest(csrf_token)
        ):
            raise AuthError("CSRF token không hợp lệ.", status_code=403, code="CSRF_INVALID")

    @staticmethod
    def _validate_registration(full_name: str, email: str, password: str) -> None:
        errors: dict[str, str] = {}
        if len(full_name.strip()) < 2:
            errors["fullName"] = "Họ tên phải có ít nhất 2 ký tự."
        if not EMAIL_RE.match(email):
            errors["email"] = "Email không hợp lệ."
        if (
            len(password) < 10
            or not re.search(r"[a-z]", password)
            or not re.search(r"[A-Z]", password)
            or not re.search(r"\d", password)
        ):
            errors["password"] = "Mật khẩu cần ít nhất 10 ký tự, gồm chữ hoa, chữ thường và số."
        if errors:
            raise AuthError(
                "Thông tin đăng ký chưa hợp lệ.",
                code="VALIDATION_ERROR",
                field_errors=errors,
            )

    @staticmethod
    def _to_user(record: UserRecord | None) -> AuthUser:
        if not record:
            raise AuthError(
                "Tài khoản không còn tồn tại.",
                status_code=401,
                code="UNAUTHENTICATED",
            )
        return AuthUser(
            id=record.id,
            email=record.email,
            full_name=record.full_name,
            role=record.role,
            status=record.status,
            avatar_url=record.avatar_url,
            bio=record.bio,
            travel_preferences=record.travel_preferences or [],
            creator_status=record.creator_status,
            creator_portfolio_urls=record.creator_portfolio_urls or [],
            created_at=record.created_at or datetime.now(timezone.utc),
        )
