from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import get_settings
from app.modules.auth.public import build_auth_service
from app.modules.knowledge_graph.public import build_knowledge_graph_service
from app.modules.observability.public import build_observability_service
from app.modules.trip_chat.public import build_trip_chat_repository


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Travel Planner Agents",
        version="0.1.0",
    )
    application.state.auth_service = build_auth_service(settings)
    application.state.knowledge_graph_service = build_knowledge_graph_service(settings)
    application.state.observability_service = build_observability_service(settings)
    application.state.trip_chat_repository = build_trip_chat_repository(settings)
    origins = [
        origin.strip()
        for origin in settings.backend_cors_origins.split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
