from dataclasses import dataclass

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.modules.auth.repository import AuthSessionRepository
from app.modules.auth.schema import LoginRequest, RegisterRequest
from app.modules.auth.security import (
    AuthTokens,
    REFRESH_TOKEN_TYPE,
    decode_token,
    hash_password,
    hash_token,
    issue_tokens,
    token_user_id,
    utc_now,
    validate_csrf,
    verify_password,
)
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.errors import AppError


@dataclass(frozen=True)
class AuthResult:
    user: User
    tokens: AuthTokens


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        sessions: AuthSessionRepository,
    ) -> None:
        self.users = users
        self.sessions = sessions

    def register(self, payload: RegisterRequest) -> AuthResult:
        email = str(payload.email).strip().lower()
        if self.users.get_by_email(email):
            raise AppError(
                status.HTTP_409_CONFLICT,
                "EMAIL_ALREADY_EXISTS",
                "Email đã được sử dụng.",
            )

        try:
            user = self.users.create_registered(
                email=email,
                full_name=payload.full_name,
                password_hash=hash_password(payload.password),
            )
            tokens = self._add_session(user)
            self.sessions.commit()
            self.users.refresh(user)
        except IntegrityError as exc:
            self.sessions.rollback()
            raise AppError(
                status.HTTP_409_CONFLICT,
                "EMAIL_ALREADY_EXISTS",
                "Email đã được sử dụng.",
            ) from exc
        return AuthResult(user=user, tokens=tokens)

    def login(self, payload: LoginRequest) -> AuthResult:
        user = self.users.get_by_email(str(payload.email))
        if not user or not verify_password(payload.password, user.password_hash):
            raise AppError(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_CREDENTIALS",
                "Email hoặc mật khẩu không đúng.",
            )
        self._ensure_active(user)

        tokens = self._add_session(user)
        self.sessions.commit()
        return AuthResult(user=user, tokens=tokens)

    def refresh(
        self,
        refresh_token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> AuthResult:
        if not refresh_token:
            raise AppError(401, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.")

        payload = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
        validate_csrf(payload, csrf_cookie, csrf_header)
        user_id = token_user_id(payload)
        session = self.sessions.get_by_jti(str(payload["jti"]))

        if not session or session.refresh_token_hash != hash_token(refresh_token):
            self.sessions.revoke_all_for_user(user_id, utc_now())
            self.sessions.commit()
            raise AppError(401, "INVALID_SESSION", "Refresh token không hợp lệ.")
        if session.revoked_at is not None:
            self.sessions.revoke_all_for_user(user_id, utc_now())
            self.sessions.commit()
            raise AppError(401, "SESSION_REUSED", "Refresh token đã được sử dụng hoặc thu hồi.")

        user = self.users.get_by_id(user_id)
        if not user:
            raise AppError(401, "INVALID_SESSION", "Tài khoản không còn tồn tại.")
        self._ensure_active(user)

        tokens = issue_tokens(user.id)
        self.sessions.revoke(session, utc_now(), tokens.refresh_jti)
        self.sessions.add(
            user_id=user.id,
            jti=tokens.refresh_jti,
            refresh_token_hash=hash_token(tokens.refresh_token),
            expires_at=tokens.refresh_expires_at,
        )
        self.sessions.commit()
        return AuthResult(user=user, tokens=tokens)

    def logout(
        self,
        refresh_token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
        except AppError:
            return
        validate_csrf(payload, csrf_cookie, csrf_header)
        session = self.sessions.get_by_jti(str(payload["jti"]))
        if session and session.revoked_at is None:
            self.sessions.revoke(session, utc_now())
            self.sessions.commit()

    def _add_session(self, user: User) -> AuthTokens:
        tokens = issue_tokens(user.id)
        self.sessions.add(
            user_id=user.id,
            jti=tokens.refresh_jti,
            refresh_token_hash=hash_token(tokens.refresh_token),
            expires_at=tokens.refresh_expires_at,
        )
        return tokens

    @staticmethod
    def _ensure_active(user: User) -> None:
        if user.status != "active":
            raise AppError(403, "ACCOUNT_NOT_ACTIVE", "Tài khoản không ở trạng thái hoạt động.")
