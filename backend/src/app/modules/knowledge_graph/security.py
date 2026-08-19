from fastapi import HTTPException, Request

from app.modules.auth.public import bearer_token


async def require_admin(request: Request):
    try:
        user = await request.app.state.auth_service.authorize(
            bearer_token(request),
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) == 401:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "Chưa đăng nhập."}) from None
        raise
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"code": "ADMIN_REQUIRED", "message": "Cần quyền admin."})
    return user


async def require_admin_write(request: Request):
    try:
        user = await request.app.state.auth_service.authorize(
            bearer_token(request),
        )
    except Exception as exc:
        status_code = getattr(exc, "status_code", 401)
        if status_code in (401, 403):
            raise HTTPException(status_code=status_code, detail={"code": "AUTHORIZATION_FAILED", "message": "Bearer token hoặc quyền admin không hợp lệ."}) from None
        raise
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"code": "ADMIN_REQUIRED", "message": "Cần quyền admin."})
    return user
