from fastapi import APIRouter, HTTPException, Request, Response

from app.modules.auth.contract import (
    AuthUser,
    CreatorApplicationInput,
    LoginInput,
    LoginResponse,
    RefreshInput,
    ProfileUpdateInput,
    RegisterInput,
)
from app.modules.auth.errors import AuthError
from app.modules.auth.service import AuthService


router = APIRouter(tags=["authentication"])


def _raise(error: AuthError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "fieldErrors": error.field_errors},
    )


def _bearer(request: Request) -> str | None:
    value = request.headers.get("Authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.casefold() == "bearer" and token.strip() else None


def _service(request: Request) -> AuthService:
    return request.app.state.auth_service


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginInput, request: Request, response: Response) -> LoginResponse:
    try:
        user, access_token, refresh_token, csrf_token = await _service(request).login(payload.email, payload.password)
    except AuthError as error:
        _raise(error)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=user, access_token=access_token, refresh_token=refresh_token, expires_in=_service(request).access_token_ttl_seconds)


@router.post("/auth/register", response_model=LoginResponse)
async def register(payload: RegisterInput, request: Request, response: Response) -> LoginResponse:
    try:
        user, access_token, refresh_token, csrf_token = await _service(request).register(payload.full_name, payload.email, payload.password)
    except AuthError as error:
        _raise(error)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=user, access_token=access_token, refresh_token=refresh_token, expires_in=_service(request).access_token_ttl_seconds)


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(request: Request, response: Response, payload: RefreshInput | None = None) -> LoginResponse:
    try:
        body_token = payload.refresh_token if payload else None
        if not body_token:
            raise AuthError("Thiếu refresh token.", status_code=401, code="INVALID_REFRESH_TOKEN")
        user, access_token, rotated_refresh_token, _ = await _service(request).refresh(
            body_token, require_csrf=False
        )
    except AuthError as error:
        _raise(error)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=user, access_token=access_token, refresh_token=rotated_refresh_token, expires_in=_service(request).access_token_ttl_seconds)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response, payload: RefreshInput | None = None) -> Response:
    try:
        await _service(request).logout(payload.refresh_token if payload else None, require_csrf=False)
    except AuthError as error:
        _raise(error)
    response.status_code = 204
    return response


@router.get("/me", response_model=AuthUser)
async def current_user(request: Request) -> AuthUser:
    user = await _service(request).user(_bearer(request))
    if not user:
        _raise(AuthError("Chưa đăng nhập.", status_code=401, code="UNAUTHENTICATED"))
    return user


@router.patch("/me/profile", response_model=AuthUser)
async def update_profile(payload: ProfileUpdateInput, request: Request) -> AuthUser:
    try:
        return await _service(request).update_profile(
            _bearer(request),
            None,
            full_name=payload.full_name,
            avatar_url=payload.avatar_url,
            bio=payload.bio,
            travel_preferences=payload.travel_preferences,
        )
    except AuthError as error:
        _raise(error)


@router.post("/me/creator-application", response_model=AuthUser)
async def creator_application(payload: CreatorApplicationInput, request: Request) -> AuthUser:
    try:
        return await _service(request).update_profile(
            _bearer(request),
            None,
            bio=payload.bio,
            creator_status="pending",
            creator_portfolio_urls=payload.portfolio_urls,
        )
    except AuthError as error:
        _raise(error)
