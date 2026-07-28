from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.modules.auth.dependencies import (
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    ACCESS_COOKIE,
    get_auth_service,
)
from app.modules.auth.schema import AuthResponse, LoginRequest, RegisterRequest
from app.modules.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def set_auth_cookies(response: Response, result: AuthResult) -> None:
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        result.tokens.access_token,
        httponly=True,
        max_age=settings.access_token_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        result.tokens.refresh_token,
        httponly=True,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        result.tokens.csrf_token,
        httponly=False,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    for cookie in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            cookie,
            secure=settings.auth_cookie_secure,
            httponly=cookie != CSRF_COOKIE,
            samesite="lax",
            path="/",
        )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    result = service.register(payload)
    set_auth_cookies(response, result)
    return AuthResponse(user=result.user)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    result = service.login(payload)
    set_auth_cookies(response, result)
    return AuthResponse(user=result.user)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    result = service.refresh(
        request.cookies.get(REFRESH_COOKIE),
        request.cookies.get(CSRF_COOKIE),
        request.headers.get(CSRF_HEADER),
    )
    set_auth_cookies(response, result)
    return AuthResponse(user=result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    service.logout(
        request.cookies.get(REFRESH_COOKIE),
        request.cookies.get(CSRF_COOKIE),
        request.headers.get(CSRF_HEADER),
    )
    clear_auth_cookies(response)
