"""Dependencies for Knowledge Graph module."""

from functools import lru_cache

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.integrations.llm.factory import get_llm_client
from app.modules.knowledge_graph.dataset import KnowledgeGraphDataset
from app.modules.knowledge_graph.repositories import (
    GraphImportRepository,
    KnowledgeGraphRepository,
)


@lru_cache(maxsize=1)
def get_knowledge_graph_dataset() -> KnowledgeGraphDataset:
    return KnowledgeGraphDataset()


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def get_knowledge_graph_repository() -> KnowledgeGraphRepository:
    """Get the PostgreSQL knowledge graph repository."""
    return KnowledgeGraphRepository(get_db())


def get_graph_import_repository() -> GraphImportRepository:
    """Get the PostgreSQL graph import repository."""
    return GraphImportRepository(get_db())


def get_knowledge_graph_import_service():
    """Get the knowledge graph import service with PostgreSQL repositories."""
    from app.modules.knowledge_graph.service import KnowledgeGraphImportService

    return KnowledgeGraphImportService(
        get_graph_import_repository(),
        get_knowledge_graph_repository(),
        get_knowledge_graph_dataset(),
        get_llm_client(),
    )
