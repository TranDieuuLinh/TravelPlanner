from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.shared.errors import AppError

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("not-a-real-user-password")


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    refresh_jti: str
    refresh_expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    candidate = encoded_hash or dummy_password_hash
    try:
        verified = password_hash.verify(password, candidate)
    except Exception:
        return False
    return bool(encoded_hash) and verified


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def issue_tokens(user_id: int) -> AuthTokens:
    now = utc_now()
    csrf_token = secrets.token_urlsafe(32)
    refresh_jti = secrets.token_hex(24)
    access_payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "jti": secrets.token_hex(24),
        "csrf": csrf_token,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    refresh_expires_at = now + timedelta(days=settings.refresh_token_days)
    refresh_payload = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "jti": refresh_jti,
        "csrf": csrf_token,
        "iat": now,
        "exp": refresh_expires_at,
    }
    return AuthTokens(
        access_token=jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm),
        refresh_token=jwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm),
        csrf_token=csrf_token,
        refresh_jti=refresh_jti,
        refresh_expires_at=refresh_expires_at,
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "jti", "csrf", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "INVALID_SESSION", "Phiên đăng nhập không hợp lệ.") from exc

    if payload.get("type") != expected_type:
        raise AppError(401, "INVALID_SESSION", "Loại token không hợp lệ.")
    return payload


def token_user_id(payload: dict[str, Any]) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(401, "INVALID_SESSION", "Danh tính trong token không hợp lệ.") from exc


def validate_csrf(payload: dict[str, Any], cookie_token: str | None, header_token: str | None) -> None:
    expected = payload.get("csrf")
    if (
        not expected
        or not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
        or not secrets.compare_digest(cookie_token, str(expected))
    ):
        raise AppError(403, "CSRF_VALIDATION_FAILED", "CSRF token không hợp lệ.")
