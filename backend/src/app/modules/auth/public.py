from app.modules.auth.contract import AuthUser
from app.modules.auth.adapters.in_memory import InMemoryUserRepository
from app.modules.auth.adapters.postgres import PostgresUserRepository
from app.modules.auth.service import AuthService
from app.core.config import Settings
from app.modules.auth.router import router
from fastapi import HTTPException, Request


async def require_current_user(request: Request) -> AuthUser:
    user = await request.app.state.auth_service.user(
        request.cookies.get("travelplanner_session")
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "Chưa đăng nhập."},
        )
    return user


async def require_admin(request: Request) -> AuthUser:
    user = await request.app.state.auth_service.user(
        request.cookies.get("travelplanner_session")
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "Chưa đăng nhập."},
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_REQUIRED", "message": "Cần quyền admin."},
        )
    return user


def build_auth_service(settings: Settings) -> AuthService:
    repository = (
        PostgresUserRepository(settings.database_url)
        if settings.database_url and settings.database_url.strip()
        else InMemoryUserRepository()
    )
    bootstrap_users: list[tuple[str, str, str, str]] = []
    if settings.app_env == "development":
        for item in settings.auth_dev_seed_users.split(","):
            parts = item.split("|", 3)
            if len(parts) == 4 and all(parts):
                bootstrap_users.append(tuple(parts))
    return AuthService(repository, bootstrap_users)


__all__ = [
    "AuthUser",
    "build_auth_service",
    "require_admin",
    "require_current_user",
    "router",
]
