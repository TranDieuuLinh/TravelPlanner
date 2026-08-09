"""Dependencies for Knowledge Graph module."""

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
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


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session and always release its connection."""
    with SessionLocal() as db:
        yield db


def get_knowledge_graph_repository(
    db: Session = Depends(get_db),
) -> KnowledgeGraphRepository:
    """Get the PostgreSQL knowledge graph repository."""
    return KnowledgeGraphRepository(db)


def get_graph_import_repository(
    db: Session = Depends(get_db),
) -> GraphImportRepository:
    """Get the PostgreSQL graph import repository."""
    return GraphImportRepository(db)


def get_knowledge_graph_import_service(
    graph_repository: GraphImportRepository = Depends(get_graph_import_repository),
    knowledge_repository: KnowledgeGraphRepository = Depends(get_knowledge_graph_repository),
):
    """Get the knowledge graph import service with PostgreSQL repositories."""
    from app.modules.knowledge_graph.service import KnowledgeGraphImportService

    return KnowledgeGraphImportService(
        graph_repository,
        knowledge_repository,
        get_knowledge_graph_dataset(),
        get_llm_client(),
    )
