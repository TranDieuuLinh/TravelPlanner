import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.models import Place, User, UserMustPlace
from app.db.session import engine
from app.modules.plans.explorer.tools.url_reels.speech_to_text import preload_audio_model
from app.shared.schemas import APIMessage

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def create_local_tables() -> None:
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(
            bind=engine,
            tables=[
                User.__table__,
                Place.__table__,
                UserMustPlace.__table__,
            ],
        )

    if settings.preload_url_reel_models:
        try:
            preload_audio_model()
            logger.info("URL reel audio model preloaded")
        except Exception:
            logger.exception("URL reel audio model preload failed")


@app.get("/health", response_model=APIMessage)
def health() -> APIMessage:
    return APIMessage(message="ok")


app.include_router(api_router)
