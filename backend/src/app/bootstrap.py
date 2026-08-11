from functools import lru_cache

from app.core.config import Settings, get_settings
from app.modules.explorer.public import build_explorer_graph, create_explorer_service
from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
    HashingEmbeddingProvider,
    InMemorySourceRepository,
)
from app.modules.information_finder.adapters.gemini_embedding import (
    GeminiEmbeddingProvider,
)
from app.modules.information_finder.adapters.llm_answer_generator import (
    StructuredLlmAnswerGenerator,
)
from app.modules.information_finder.adapters.postgres_source_repository import (
    PostgresSourceRepository,
)
from app.modules.information_finder.adapters.tavily_search import TavilySearchProvider
from app.modules.information_finder.ports import (
    AnswerGenerator,
    EmbeddingProvider,
    SourceRepository,
)
from app.modules.information_finder.service import (
    InformationFinderOptions,
    InformationFinderService,
)
from app.modules.supervisor.adapters import GeminiIntentClassifier
from app.modules.supervisor.public import SupervisorService
from app.orchestration.root_graph import create_root_graph
from app.shared.llm import GeminiLlmClient, LlmClient


def create_answer_generator(
    settings: Settings,
    llm_client: LlmClient | None = None,
) -> AnswerGenerator:
    if settings.information_finder_answer_provider == "extractive":
        return ExtractiveAnswerGenerator()
    return StructuredLlmAnswerGenerator(
        llm_client
        or GeminiLlmClient(
            settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
        ),
        max_output_tokens=settings.information_finder_llm_max_output_tokens,
        max_chars_per_source=settings.information_finder_llm_max_chars_per_source,
        max_total_source_chars=(settings.information_finder_llm_max_total_source_chars),
    )


@lru_cache
def get_information_finder_service() -> InformationFinderService:
    settings = get_settings()
    if settings.database_url:
        repository: SourceRepository = PostgresSourceRepository(settings.database_url)
        if settings.gemini_api_key:
            embeddings: EmbeddingProvider = GeminiEmbeddingProvider(
                settings.gemini_api_key,
                model_name=settings.information_finder_embedding_model,
                model_revision=settings.information_finder_embedding_revision,
                dimensions=settings.information_finder_embedding_output_dimensions,
                timeout_seconds=settings.information_finder_embedding_timeout_seconds,
                key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
            )
        elif settings.app_env in ("development", "test"):
            embeddings = HashingEmbeddingProvider()
        else:
            raise ValueError(
                "GEMINI_API_KEY is required for PostgreSQL Information Finder embeddings"
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
    answers = create_answer_generator(
        settings,
        get_llm_client()
        if settings.information_finder_answer_provider == "gemini"
        else None,
    )
    fallback_answers = (
        ExtractiveAnswerGenerator()
        if settings.information_finder_answer_provider != "extractive"
        else None
    )
    return InformationFinderService(
        repository=repository,
        embeddings=embeddings,
        answers=answers,
        fallback_answers=fallback_answers,
        search_provider=search_provider,
        options=InformationFinderOptions(
            minimum_local_sources=settings.information_finder_min_local_sources,
            similarity_threshold=settings.information_finder_similarity_threshold,
            provider_relevance_threshold=settings.information_finder_relevance_threshold,
            blocked_domains=blocked_domains,
            answer_fallback_enabled=(settings.information_finder_llm_fallback_enabled),
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


def create_supervisor_service(
    settings: Settings,
    llm_client: LlmClient | None = None,
) -> SupervisorService:
    classifier = None
    if settings.supervisor_classifier_provider == "gemini":
        classifier = GeminiIntentClassifier(
            llm_client
            or GeminiLlmClient(
                settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
                key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
            ),
            max_output_tokens=settings.supervisor_llm_max_output_tokens,
        )
    return SupervisorService(
        classifier,
        fallback_enabled=settings.supervisor_llm_fallback_enabled,
        confidence_threshold=settings.supervisor_llm_confidence_threshold,
    )


def compose_explorer_service(
    settings: Settings,
    llm_client: LlmClient | None = None,
) -> object:
    client = llm_client
    if settings.gemini_api_key and client is None:
        client = GeminiLlmClient(
            settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
        )
    image_client = None
    audio_client = None
    if settings.gemini_api_key:
        common_options = {
            "timeout_seconds": settings.gemini_timeout_seconds,
            "key_cooldown_seconds": settings.gemini_key_cooldown_seconds,
        }
        image_client = GeminiLlmClient(
            settings.gemini_api_key,
            model=settings.gemini_image_ocr_model,
            **common_options,
        )
        audio_client = GeminiLlmClient(
            settings.gemini_api_key,
            model=settings.gemini_audio_model,
            **common_options,
        )
    return create_explorer_service(
        draft_provider=settings.explorer_draft_provider,
        llm_client=client,
        image_llm_client=image_client,
        audio_llm_client=audio_client,
        max_output_tokens=settings.explorer_llm_max_output_tokens,
        url_timeout_seconds=settings.explorer_url_timeout_seconds,
        ytdlp_cookie_file=settings.explorer_ytdlp_cookie_file,
        frame_interval_seconds=settings.explorer_frame_interval_seconds,
        frame_batch_size=settings.explorer_frame_batch_size,
        max_frames=settings.explorer_max_frames,
        frame_max_concurrency=settings.explorer_frame_max_concurrency,
        audio_chunk_count=settings.explorer_audio_chunk_count,
        max_video_seconds=settings.explorer_max_video_seconds,
        max_media_mb=settings.explorer_max_media_mb,
        database_url=settings.database_url,
        url_cache_ttl_seconds=settings.explorer_url_cache_ttl_seconds,
        draft_cache_ttl_seconds=settings.explorer_draft_cache_ttl_seconds,
        draft_cache_namespace=(
            f"v1:{settings.explorer_draft_provider}:{settings.gemini_model}"
        ),
    )


@lru_cache
def get_explorer_graph():
    settings = get_settings()
    client = get_llm_client() if settings.gemini_api_key else None
    return build_explorer_graph(compose_explorer_service(settings, client))


@lru_cache
def get_graph():
    settings = get_settings()
    shared_llm_client = None
    if (
        settings.supervisor_classifier_provider == "gemini"
        or settings.information_finder_answer_provider == "gemini"
        or settings.explorer_draft_provider == "gemini"
        or bool(settings.gemini_api_key)
    ):
        shared_llm_client = get_llm_client()
    return create_root_graph(
        information_finder_service=get_information_finder_service(),
        supervisor_service=create_supervisor_service(settings, shared_llm_client),
        explorer_service=compose_explorer_service(settings, shared_llm_client),
    )
