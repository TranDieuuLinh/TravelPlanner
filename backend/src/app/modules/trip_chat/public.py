from app.core.config import Settings
from app.modules.trip_chat.adapters.postgres import PostgresTripChatRepository
from app.modules.trip_chat.router import router


def build_trip_chat_repository(settings: Settings) -> PostgresTripChatRepository:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for durable trip-chat storage")
    return PostgresTripChatRepository(settings.database_url)

__all__ = ["build_trip_chat_repository", "router"]
