import time
from collections import defaultdict
from typing import Dict, List
from fastapi.responses import JSONResponse
from starlette.requests import Request

# Simple in-memory rate limiter per IP for sensitive paths
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW_SEC = 60
_MAX_REQUESTS_PER_WINDOW = 60
_SENSITIVE_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/checkout-sessions",
)


def _is_rate_limited(client_ip: str, now: float) -> bool:
    timestamps = _rate_limit_store[client_ip]
    # Remove timestamps outside window
    timestamps = [ts for ts in timestamps if now - ts < _RATE_LIMIT_WINDOW_SEC]
    if len(timestamps) >= _MAX_REQUESTS_PER_WINDOW:
        _rate_limit_store[client_ip] = timestamps
        return True
    timestamps.append(now)
    _rate_limit_store[client_ip] = timestamps
    return False


def reset_rate_limit_store() -> None:
    """Helper method for unit tests to reset in-memory rate limit store."""
    _rate_limit_store.clear()


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(prefix) for prefix in _SENSITIVE_PREFIXES):
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        if _is_rate_limited(client_ip, now):
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Quá nhiều yêu cầu, vui lòng thử lại sau.",
                },
            )
    return await call_next(request)


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
