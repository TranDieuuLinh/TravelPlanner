import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import Settings, get_settings
from app.modules.auth.public import build_auth_service
from app.modules.conversation_memory.public import build_conversation_memory_service
from app.modules.knowledge_graph.public import build_knowledge_graph_service
from app.modules.itinerary_planner.public import build_valhalla_directions_service
from app.modules.observability.public import build_observability_service
from app.modules.trip_chat.public import build_trip_chat_repository
from app.bootstrap import get_graph


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        auth_service = application.state.auth_service
        trip_repository = application.state.trip_chat_repository
        # Warm auth opportunistically so the first /me is normally hot. A
        # temporarily unavailable external database must not prevent the API
        # process (or isolated API tests) from starting.
        await asyncio.gather(auth_service.ensure_ready(), return_exceptions=True)
        try:
            yield
        finally:
            closers = []
            auth_close = getattr(auth_service.repository, "close", None)
            if auth_close is not None:
                closers.append(auth_close())
            trip_close = getattr(trip_repository, "close", None)
            if trip_close is not None:
                closers.append(trip_close())
            memory_service = getattr(application.state, "conversation_memory_service", None)
            repository = getattr(memory_service, "repository", None)
            close = getattr(repository, "close", None)
            if close is not None:
                closers.append(close())
            # get_graph is lazy/cached. Close its durable checkpoint connection
            # on reload/shutdown so development reloads cannot hang or leak a
            # cloud PostgreSQL session.
            if get_graph.cache_info().currsize:
                checkpointer = getattr(get_graph(), "checkpointer", None)
                checkpoint_close = getattr(checkpointer, "aclose", None)
                if checkpoint_close is not None:
                    closers.append(checkpoint_close())
            obs_service = getattr(application.state, "observability_service", None)
            obs_close = getattr(obs_service, "aclose", None)
            if obs_close is not None:
                closers.append(obs_close())
            if closers:
                await asyncio.gather(*closers)

    application = FastAPI(
        title="Travel Planner Agents",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def add_trace_id_header(request, call_next):
        response = await call_next(request)
        trace_id = getattr(request.state, "trace_id", None)
        if trace_id:
            response.headers["X-Trace-ID"] = str(trace_id)
        return response

    application.state.auth_service = build_auth_service(settings)
    application.state.knowledge_graph_service = build_knowledge_graph_service(settings)
    application.state.observability_service = build_observability_service(settings)
    application.state.trip_chat_repository = build_trip_chat_repository(settings)
    application.state.conversation_memory_service = (
        build_conversation_memory_service(settings)
        if settings.conversation_memory_enabled
        else None
    )
    application.state.directions_service = build_valhalla_directions_service(
        settings.valhalla_base_url,
        timeout_seconds=settings.valhalla_timeout_seconds,
        provider_version=settings.valhalla_graph_version,
    )
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
