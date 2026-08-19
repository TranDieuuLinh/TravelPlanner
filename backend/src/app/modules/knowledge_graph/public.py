from app.core.config import Settings
from app.modules.knowledge_graph.adapters.draft_places import PostgresDraftPlaceStore
from app.modules.knowledge_graph.adapters.postgres import PostgresKnowledgeGraphStore
from app.modules.knowledge_graph.contract import EntityPreview
from app.modules.knowledge_graph.router import public_router, router
from app.modules.knowledge_graph.service import KnowledgeGraphService


def build_knowledge_graph_service(settings: Settings) -> KnowledgeGraphService | None:
    if not settings.database_url:
        return None
    return KnowledgeGraphService(PostgresKnowledgeGraphStore(settings.database_url))


def build_draft_place_store(database_url: str) -> PostgresDraftPlaceStore:
    return PostgresDraftPlaceStore(database_url)


__all__ = [
    "build_draft_place_store",
    "build_knowledge_graph_service",
    "EntityPreview",
    "public_router",
    "router",
]
