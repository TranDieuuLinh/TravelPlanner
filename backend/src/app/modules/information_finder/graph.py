from langgraph.graph import END, START, StateGraph

from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
    HashingEmbeddingProvider,
    InMemorySourceRepository,
)
from app.modules.information_finder.nodes import create_find_node
from app.modules.information_finder.service import InformationFinderService
from app.modules.information_finder.state import InformationFinderState


def create_development_service() -> InformationFinderService:
    return InformationFinderService(
        repository=InMemorySourceRepository(),
        embeddings=HashingEmbeddingProvider(),
        answers=ExtractiveAnswerGenerator(),
    )


def build_information_finder_graph(service: InformationFinderService | None = None):
    builder = StateGraph(InformationFinderState)
    builder.add_node("find", create_find_node(service or create_development_service()))
    builder.add_edge(START, "find")
    builder.add_edge("find", END)
    return builder.compile()

