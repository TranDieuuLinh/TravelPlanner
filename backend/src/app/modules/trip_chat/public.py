from app.core.config import Settings
from app.modules.trip_chat.adapters.in_memory import InMemoryTripChatRepository
from app.modules.trip_chat.adapters.postgres import PostgresTripChatRepository
from app.modules.trip_chat.ports import TripChatRepository
from app.modules.trip_chat.router import router
from app.modules.trip_chat.plan_mutations_router import router as plan_mutations_router


def build_trip_chat_repository(settings: Settings) -> TripChatRepository:
    if settings.database_url:
        return PostgresTripChatRepository(settings.database_url)
    return InMemoryTripChatRepository()


__all__ = ["InMemoryTripChatRepository", "build_trip_chat_repository", "router", "plan_mutations_router"]
