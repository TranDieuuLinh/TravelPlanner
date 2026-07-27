from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.models import User
from app.db.session import engine
from app.shared.schemas import APIMessage

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
        Base.metadata.create_all(bind=engine, tables=[User.__table__])


@app.get("/health", response_model=APIMessage)
def health() -> APIMessage:
    return APIMessage(message="ok")


app.include_router(api_router)
