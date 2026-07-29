import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api_router import api_router
from app.core.config import settings
from app.core.security_headers import (
    rate_limit_middleware,
    security_headers_middleware,
)
from app.db.models import Place, User, UserMustPlace  # noqa: F401
from app.db import models as db_models  # noqa: F401
from app.db.session import SessionLocal, engine
from app.db.seed import seed_demo_marketplace
from app.modules.plans.explorer.tools.url_reels.speech_to_text import (
    preload_audio_model,
)
from app.shared.errors import AppError
from app.shared.schemas import APIMessage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        seed_demo_marketplace(db)
    if settings.preload_url_reel_models:
        try:
            preload_audio_model()
            logger.info("URL reel audio model preloaded")
        except Exception:
            logger.exception("URL reel audio model preload failed")
    yield

    if getattr(settings, "preload_url_reel_models", False):
        try:
            preload_audio_model()
            logger.info("URL reel audio model preloaded")
        except Exception:
            logger.exception("URL reel audio model preload failed")

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers_wrapper(request: Request, call_next):
    return await security_headers_middleware(request, call_next)


@app.middleware("http")
async def rate_limit_wrapper(request: Request, call_next):
    return await rate_limit_middleware(request, call_next)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "fieldErrors": exc.field_errors,
            "requestId": getattr(request.state, "request_id", uuid4().hex),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part not in {"body", "query"})
        message = str(error["msg"])
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        field_errors[location or "request"] = message
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Dữ liệu gửi lên không hợp lệ.",
            "fieldErrors": field_errors,
            "requestId": getattr(request.state, "request_id", uuid4().hex),
        },
    )

@app.get("/health", response_model=APIMessage)
def health() -> APIMessage:
    return APIMessage(message="ok")


app.include_router(api_router)
