from functools import lru_cache

from app.core.config import get_settings
from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
    HashingEmbeddingProvider,
    InMemorySourceRepository,
)
from app.modules.information_finder.adapters.multilingual_e5 import (
    MultilingualE5EmbeddingProvider,
)
from app.modules.information_finder.adapters.postgres_source_repository import (
    PostgresSourceRepository,
)
from app.modules.information_finder.adapters.tavily_search import TavilySearchProvider
from app.modules.information_finder.ports import EmbeddingProvider, SourceRepository
from app.modules.information_finder.service import (
    InformationFinderOptions,
    InformationFinderService,
)
from app.orchestration.root_graph import create_root_graph
from app.shared.llm import GeminiLlmClient


@lru_cache
def get_information_finder_service() -> InformationFinderService:
    settings = get_settings()
    if settings.database_url:
        repository: SourceRepository = PostgresSourceRepository(settings.database_url)
        embeddings: EmbeddingProvider = MultilingualE5EmbeddingProvider(
            settings.information_finder_embedding_model,
            settings.information_finder_embedding_revision,
        )
    else:
        repository = InMemorySourceRepository()
        embeddings = HashingEmbeddingProvider()

    search_provider = None
    if settings.tavily_api_key:
        search_provider = TavilySearchProvider(
            settings.tavily_api_key,
            search_depth=settings.tavily_search_depth,
            max_results=settings.tavily_max_results,
            timeout_seconds=settings.tavily_timeout_seconds,
        )
    blocked_domains = tuple(
        domain.strip().casefold()
        for domain in settings.information_finder_blocked_domains.split(",")
        if domain.strip()
    )
    return InformationFinderService(
        repository=repository,
        embeddings=embeddings,
        answers=ExtractiveAnswerGenerator(),
        search_provider=search_provider,
        options=InformationFinderOptions(
            minimum_local_sources=settings.information_finder_min_local_sources,
            similarity_threshold=settings.information_finder_similarity_threshold,
            provider_relevance_threshold=settings.information_finder_relevance_threshold,
            blocked_domains=blocked_domains,
        ),
    )


@lru_cache
def get_llm_client() -> GeminiLlmClient:
    settings = get_settings()
    return GeminiLlmClient(
        settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
    )


@lru_cache
def get_graph():
    return create_root_graph(
        information_finder_service=get_information_finder_service()
    )
