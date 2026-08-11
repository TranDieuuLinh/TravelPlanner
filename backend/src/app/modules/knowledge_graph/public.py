from app.core.config import Settings
from app.modules.knowledge_graph.adapters.postgres import PostgresKnowledgeGraphStore
from app.modules.knowledge_graph.router import router
from app.modules.knowledge_graph.service import KnowledgeGraphService


def build_knowledge_graph_service(settings: Settings) -> KnowledgeGraphService | None:
    if not settings.database_url:
        return None
    return KnowledgeGraphService(PostgresKnowledgeGraphStore(settings.database_url))


__all__ = ["build_knowledge_graph_service", "router"]
