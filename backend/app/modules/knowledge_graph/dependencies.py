from functools import lru_cache

from app.integrations.llm.factory import get_llm_client
from app.modules.knowledge_graph.dataset import KnowledgeGraphDataset
from app.modules.knowledge_graph.repository import GraphImportRepository
from app.modules.knowledge_graph.service import KnowledgeGraphImportService


@lru_cache(maxsize=1)
def get_graph_import_repository() -> GraphImportRepository:
    return GraphImportRepository()


@lru_cache(maxsize=1)
def get_knowledge_graph_dataset() -> KnowledgeGraphDataset:
    return KnowledgeGraphDataset()


def get_knowledge_graph_import_service() -> KnowledgeGraphImportService:
    return KnowledgeGraphImportService(
        get_graph_import_repository(),
        get_knowledge_graph_dataset(),
        get_llm_client(),
    )
