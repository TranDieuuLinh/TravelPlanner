from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.repository import AuthSessionRepository
from app.modules.auth.security import ACCESS_TOKEN_TYPE, decode_token, token_user_id, validate_csrf
from app.modules.auth.service import AuthService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import UserRole
from app.shared.errors import AppError

ACCESS_COOKIE = "travelplanner_access"
REFRESH_COOKIE = "travelplanner_refresh"
CSRF_COOKIE = "travelplanner_csrf"
CSRF_HEADER = "X-CSRF-Token"


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(UserRepository(db), AuthSessionRepository(db))


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AppError(401, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.")
    payload = decode_token(token, ACCESS_TOKEN_TYPE)
    user = UserRepository(db).get_by_id(token_user_id(payload))
    if not user:
        raise AppError(401, "INVALID_SESSION", "Tài khoản không còn tồn tại.")
    if user.status != "active":
        raise AppError(403, "ACCOUNT_NOT_ACTIVE", "Tài khoản không ở trạng thái hoạt động.")
    return user


def get_optional_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    payload = decode_token(token, ACCESS_TOKEN_TYPE)
    user = UserRepository(db).get_by_id(token_user_id(payload))
    if not user:
        raise AppError(401, "INVALID_SESSION", "Tài khoản không còn tồn tại.")
    if user.status != "active":
        raise AppError(
            403,
            "ACCOUNT_NOT_ACTIVE",
            "Tài khoản không ở trạng thái hoạt động.",
        )
    validate_csrf(
        payload,
        request.cookies.get(CSRF_COOKIE),
        request.headers.get(CSRF_HEADER),
    )
    return user


def get_optional_active_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Resolve a valid active session without requiring authentication."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        payload = decode_token(token, ACCESS_TOKEN_TYPE)
        user = UserRepository(db).get_by_id(token_user_id(payload))
    except Exception:
        return None
    return user if user and user.status == "active" else None


def require_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


def require_csrf(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        raise AppError(401, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.")
    payload = decode_token(access_token, ACCESS_TOKEN_TYPE)
    validate_csrf(
        payload,
        request.cookies.get(CSRF_COOKIE),
        request.headers.get(CSRF_HEADER),
    )
    return user


def require_role(*roles: UserRole | str) -> Callable[..., User]:
    allowed = {str(role) for role in roles}

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise AppError(403, "INSUFFICIENT_ROLE", "Bạn không có quyền thực hiện hành động này.")
        return user

    return dependency
