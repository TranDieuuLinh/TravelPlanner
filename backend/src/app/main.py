from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import Settings, get_settings
from app.modules.auth.public import build_auth_service
from app.modules.conversation_memory.public import build_conversation_memory_service
from app.modules.knowledge_graph.public import build_knowledge_graph_service
from app.modules.observability.public import build_observability_service
from app.modules.trip_chat.public import build_trip_chat_repository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            memory_service = getattr(application.state, "conversation_memory_service", None)
            repository = getattr(memory_service, "repository", None)
            close = getattr(repository, "close", None)
            if close is not None:
                await close()

    application = FastAPI(
        title="Travel Planner Agents",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.auth_service = build_auth_service(settings)
    application.state.knowledge_graph_service = build_knowledge_graph_service(settings)
    application.state.observability_service = build_observability_service(settings)
    application.state.trip_chat_repository = build_trip_chat_repository(settings)
    application.state.conversation_memory_service = build_conversation_memory_service(settings)
    origins = [
        origin.strip()
        for origin in settings.backend_cors_origins.split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
