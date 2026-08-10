from fastapi import FastAPI

from app.api.router import router


def create_app() -> FastAPI:
    application = FastAPI(
        title="Travel Planner Agents",
        version="0.1.0",
    )
    application.include_router(router)
    return application


app = create_app()
