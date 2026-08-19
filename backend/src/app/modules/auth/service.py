import re
import secrets
import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg

from app.modules.auth.contract import AuthUser
from app.modules.auth.errors import AuthError
from app.modules.auth.ports import SessionRecord, UserRecord, UserRepository
from app.modules.auth.security import create_jwt, decode_jwt, token_digest


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        bootstrap_users: list[tuple[str, str, str, str]] | None = None,
        *,
        jwt_secret: str = "development-only-change-this-jwt-secret",
        access_token_ttl_seconds: int = 900,
        refresh_token_ttl_seconds: int = 604800,
    ) -> None:
        self.repository = repository
        self.bootstrap_users = bootstrap_users or []
        self.jwt_secret = jwt_secret
        self.access_token_ttl_seconds = access_token_ttl_seconds
        self.refresh_token_ttl_seconds = refresh_token_ttl_seconds
        self._ready = False

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        for email, full_name, password, role in self.bootstrap_users:
            await self.repository.ensure_user(email, full_name, password, role)
        self._ready = True

    async def user(self, access_token: str | None) -> AuthUser | None:
        await self.ensure_ready()
        claims = self._claims(access_token, "access")
        if not claims:
            return None
        return self._to_user(await self.repository.by_id(int(claims["sub"])))

    async def authorize(
        self, access_token: str | None, csrf_token: str | None = None, *, require_csrf: bool = False
    ) -> AuthUser:
        """Resolve a session for feature modules without exposing session internals."""
        await self.ensure_ready()
        del csrf_token, require_csrf
        claims = self._claims(access_token, "access")
        if not claims:
            raise AuthError("Chưa đăng nhập.", status_code=401, code="UNAUTHENTICATED")
        return self._to_user(await self.repository.by_id(int(claims["sub"])))

    async def login(self, email: str, password: str) -> tuple[AuthUser, str, str, str]:
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
    ) -> tuple[AuthUser, str, str, str]:
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
        self,
        refresh_token: str | None,
        csrf_token: str | None = None,
        *,
        require_csrf: bool = True,
    ) -> tuple[AuthUser, str, str, str]:
        claims = self._claims(refresh_token, "refresh")
        if not claims:
            raise AuthError("Refresh token không hợp lệ hoặc đã hết hạn.", status_code=401, code="INVALID_REFRESH_TOKEN")
        session = await self._session_by_refresh_token(refresh_token)
        if not session:
            raise AuthError("Refresh token đã bị thu hồi.", status_code=401, code="INVALID_REFRESH_TOKEN")
        if require_csrf:
            self._require_csrf(session, csrf_token)
        record = await self.repository.by_id(int(claims["sub"]))
        if not record:
            raise AuthError(
                "Phiên đăng nhập không còn hợp lệ.",
                status_code=401,
                code="UNAUTHENTICATED",
            )
        await self.repository.delete_session(token_digest(refresh_token or ""))
        return await self._start_session(record)

    async def logout(
        self, refresh_token: str | None, csrf_token: str | None = None, *, require_csrf: bool = True
    ) -> None:
        if not self._claims(refresh_token, "refresh"):
            return
        session = await self._session_by_refresh_token(refresh_token)
        if session:
            if require_csrf:
                self._require_csrf(session, csrf_token)
            await self.repository.delete_session(token_digest(refresh_token or ""))

    async def update_profile(
        self, access_token: str | None, csrf_token: str | None, **changes: object
    ) -> AuthUser:
        del csrf_token
        claims = self._claims(access_token, "access")
        if not claims:
            raise AuthError("Chưa đăng nhập.", status_code=401, code="UNAUTHENTICATED")
        record = await self.repository.update_user(int(claims["sub"]), **changes)
        return self._to_user(record)

    async def _start_session(self, record: UserRecord) -> tuple[AuthUser, str, str, str]:
        access_token = create_jwt(
            subject=record.id,
            token_type="access",
            role=record.role,
            secret=self.jwt_secret,
            ttl_seconds=self.access_token_ttl_seconds,
        )
        refresh_token = create_jwt(
            subject=record.id,
            token_type="refresh",
            role=record.role,
            secret=self.jwt_secret,
            ttl_seconds=self.refresh_token_ttl_seconds,
        )
        csrf_token = secrets.token_urlsafe(24)
        await self.repository.create_session(
            token_digest(refresh_token),
            record.id,
            token_digest(csrf_token),
            datetime.now(timezone.utc)
            + timedelta(seconds=self.refresh_token_ttl_seconds),
        )
        return self._to_user(record), access_token, refresh_token, csrf_token

    def _claims(self, token: str | None, token_type: str) -> dict | None:
        if not token:
            return None
        return decode_jwt(token, secret=self.jwt_secret, expected_type=token_type)

    async def _session_by_refresh_token(self, refresh_token: str | None) -> SessionRecord | None:
        if not refresh_token:
            return None
        token_hash = token_digest(refresh_token)
        # Aiven/cloud PostgreSQL may close an idle connection between requests.
        # Retry only connection-level failures; authentication and SQL errors
        # must still surface normally.
        for attempt in range(2):
            try:
                return await self.repository.session_by_token(token_hash)
            except (asyncpg.PostgresConnectionError, ConnectionError):
                if attempt == 1:
                    raise
                await asyncio.sleep(0.2)
        return None

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
