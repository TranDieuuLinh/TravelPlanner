from fastapi import APIRouter, HTTPException, Request, Response

from app.modules.auth.contract import (
    AuthUser,
    CreatorApplicationInput,
    LoginInput,
    LoginResponse,
    ProfileUpdateInput,
    RegisterInput,
)
from app.modules.auth.errors import AuthError
from app.modules.auth.service import AuthService


router = APIRouter(tags=["authentication"])
SESSION_COOKIE = "travelplanner_session"
CSRF_COOKIE = "travelplanner_csrf"


def _raise(error: AuthError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, "fieldErrors": error.field_errors},
    )


def _set_session(response: Response, token: str, csrf_token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=604800, samesite="lax")
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, max_age=604800, samesite="lax")


def _clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


def _csrf(request: Request) -> str | None:
    return request.headers.get("X-CSRF-Token")


def _service(request: Request) -> AuthService:
    return request.app.state.auth_service


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginInput, request: Request, response: Response) -> LoginResponse:
    try:
        user, token, csrf_token = await _service(request).login(payload.email, payload.password)
    except AuthError as error:
        _raise(error)
    _set_session(response, token, csrf_token)
    return LoginResponse(user=user)


@router.post("/auth/register", response_model=LoginResponse)
async def register(payload: RegisterInput, request: Request, response: Response) -> LoginResponse:
    try:
        user, token, csrf_token = await _service(request).register(payload.full_name, payload.email, payload.password)
    except AuthError as error:
        _raise(error)
    _set_session(response, token, csrf_token)
    return LoginResponse(user=user)


@router.post("/auth/refresh", status_code=204)
async def refresh(request: Request, response: Response) -> Response:
    try:
        user, token, csrf_token = await _service(request).refresh(request.cookies.get(SESSION_COOKIE), _csrf(request))
    except AuthError as error:
        _raise(error)
    del user
    _set_session(response, token, csrf_token)
    response.status_code = 204
    return response


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    try:
        await _service(request).logout(request.cookies.get(SESSION_COOKIE), _csrf(request))
    except AuthError as error:
        _raise(error)
    _clear_session(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=AuthUser)
async def current_user(request: Request) -> AuthUser:
    user = await _service(request).user(request.cookies.get(SESSION_COOKIE))
    if not user:
        _raise(AuthError("Chưa đăng nhập.", status_code=401, code="UNAUTHENTICATED"))
    return user


@router.patch("/me/profile", response_model=AuthUser)
async def update_profile(payload: ProfileUpdateInput, request: Request) -> AuthUser:
    try:
        return await _service(request).update_profile(
            request.cookies.get(SESSION_COOKIE),
            _csrf(request),
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
            request.cookies.get(SESSION_COOKIE),
            _csrf(request),
            bio=payload.bio,
            creator_status="pending",
            creator_portfolio_urls=payload.portfolio_urls,
        )
    except AuthError as error:
        _raise(error)
