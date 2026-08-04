"""Repositories for Knowledge Graph."""

from app.modules.knowledge_graph.repositories.kg_repository import (
    KnowledgeGraphRepository,
)
from app.modules.knowledge_graph.repositories.import_repository import (
    GraphImportRepository,
)

__all__ = ["KnowledgeGraphRepository", "GraphImportRepository"]
