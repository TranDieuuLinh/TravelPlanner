import asyncio
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
from app.modules.information_finder.adapters.gemini_url_chunker import (
    GeminiUrlSourceChunker,
)
from app.modules.information_finder.adapters.llm_answer_generator import (
    StructuredLlmAnswerGenerator,
)
from app.modules.information_finder.adapters.llm_search_query_planner import (
    LlmSearchQueryPlanner,
)
from app.modules.information_finder.adapters.postgres_source_repository import (
    PostgresSourceRepository,
)
from app.modules.information_finder.adapters.tavily_search import TavilySearchProvider
from app.modules.information_finder.entity_linking import KnowledgeGraphEntityResolver
from app.modules.information_finder.tools.budget_ranges import BudgetRangeTool
from app.modules.information_finder.ports import (
    AnswerGenerator,
    EmbeddingProvider,
    SourceRepository,
)
from app.modules.information_finder.service import (
    InformationFinderOptions,
    InformationFinderService,
)
from app.modules.itinerary_planner.public import (
    build_valhalla_beam_first_itinerary_planner_graph,
)
from app.modules.knowledge_graph.public import (
    build_draft_place_store,
    build_knowledge_graph_service,
)
from app.modules.place_checker.public import build_postgres_place_checker_pipeline
from app.modules.supervisor.adapters import GeminiIntentClassifier, GeminiResponseComposer
from app.modules.supervisor.public import SupervisorService
from app.orchestration.root_graph import create_root_graph
from app.shared.llm import GeminiKeyPool, GeminiLlmClient, LlmClient
from app.shared.tools.search_places.adapters import GoogleMapsPlaywrightSearch


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
    search_query_planner = (
        LlmSearchQueryPlanner(get_llm_client())
        if settings.gemini_api_key and search_provider is not None
        else None
    )
    knowledge_graph = build_knowledge_graph_service(settings)
    entity_resolver = (
        KnowledgeGraphEntityResolver(knowledge_graph.entity_preview)
        if knowledge_graph is not None
        else None
    )
    blocked_domains = tuple(
        domain.strip().casefold()
        for domain in settings.information_finder_blocked_domains.split(",")
        if domain.strip()
    )
    chunker = None
    if (
        settings.information_finder_chunking_provider == "gemini_url"
        and settings.gemini_api_key
    ):
        chunker = GeminiUrlSourceChunker(
            get_llm_client(),
            max_output_tokens=settings.information_finder_chunking_max_output_tokens,
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
        chunker=chunker,
        search_provider=search_provider,
        search_query_planner=search_query_planner,
        entity_resolver=entity_resolver,
        budget_ranges=(BudgetRangeTool(knowledge_graph) if knowledge_graph is not None else None),
        options=InformationFinderOptions(
            provider_relevance_threshold=settings.information_finder_relevance_threshold,
            blocked_domains=blocked_domains,
            answer_fallback_enabled=(settings.information_finder_llm_fallback_enabled),
        ),
    )


@lru_cache
def get_gemini_key_pool() -> GeminiKeyPool:
    settings = get_settings()
    return GeminiKeyPool(
        settings.gemini_api_key,
        default_cooldown_seconds=settings.gemini_key_cooldown_seconds,
        per_key_max_in_flight=1,
    )


@lru_cache
def get_explorer_synthesis_limiter() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().explorer_synthesis_max_concurrency)


@lru_cache
def get_llm_client() -> GeminiLlmClient:
    settings = get_settings()
    return GeminiLlmClient(
        settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
        key_pool=get_gemini_key_pool(),
    )


def create_supervisor_service(
    settings: Settings,
    llm_client: LlmClient | None = None,
) -> SupervisorService:
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
    composer = GeminiResponseComposer(
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
        composer,
        fallback_enabled=settings.supervisor_llm_fallback_enabled,
        confidence_threshold=settings.supervisor_llm_confidence_threshold,
    )


def compose_explorer_service(
    settings: Settings,
    llm_client: LlmClient | None = None,
    synthesis_limiter: asyncio.Semaphore | None = None,
) -> object:
    client = llm_client
    key_pool = getattr(client, "key_pool", None)
    if settings.gemini_api_key and key_pool is None:
        key_pool = GeminiKeyPool(
            settings.gemini_api_key,
            default_cooldown_seconds=settings.gemini_key_cooldown_seconds,
            per_key_max_in_flight=1,
        )
    if settings.gemini_api_key and client is None:
        client = GeminiLlmClient(
            settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            key_cooldown_seconds=settings.gemini_key_cooldown_seconds,
            key_pool=key_pool,
        )
    image_client = None
    audio_client = None
    if settings.gemini_api_key:
        common_options = {
            "timeout_seconds": settings.gemini_timeout_seconds,
            "key_cooldown_seconds": settings.gemini_key_cooldown_seconds,
            "key_pool": key_pool,
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
        source_draft_provider=settings.explorer_source_draft_provider,
        llm_client=client,
        image_llm_client=image_client,
        audio_llm_client=audio_client,
        max_output_tokens=settings.explorer_llm_max_output_tokens,
        source_chunk_characters=settings.explorer_source_chunk_characters,
        source_max_output_tokens=settings.explorer_source_max_output_tokens,
        source_max_concurrency=settings.explorer_source_max_concurrency,
        synthesis_max_concurrency=settings.explorer_synthesis_max_concurrency,
        synthesis_limiter=synthesis_limiter,
        dedupe_provider=settings.explorer_dedupe_provider,
        note_provider=settings.explorer_note_provider,
        url_timeout_seconds=settings.explorer_url_timeout_seconds,
        source_extraction_timeout_seconds=(
            settings.explorer_source_extraction_timeout_seconds
        ),
        source_synthesis_timeout_seconds=(
            settings.explorer_source_synthesis_timeout_seconds
        ),
        source_chunk_timeout_seconds=settings.explorer_source_chunk_timeout_seconds,
        ytdlp_cookie_file=settings.explorer_ytdlp_cookie_file,
        frame_interval_seconds=settings.explorer_frame_interval_seconds,
        frame_batch_size=settings.explorer_frame_batch_size,
        max_frames=settings.explorer_max_frames,
        frame_max_concurrency=settings.explorer_frame_max_concurrency,
        audio_chunk_count=settings.explorer_audio_chunk_count,
        audio_chunk_seconds=settings.explorer_audio_chunk_seconds,
        youtube_audio_chunk_seconds=settings.explorer_youtube_audio_chunk_seconds,
        youtube_audio_chunk_overlap_seconds=(
            settings.explorer_youtube_audio_chunk_overlap_seconds
        ),
        youtube_audio_max_concurrency=(
            settings.explorer_youtube_audio_max_concurrency
        ),
        youtube_max_duration_seconds=settings.explorer_youtube_max_duration_seconds,
        max_video_seconds=settings.explorer_max_video_seconds,
        max_media_mb=settings.explorer_max_media_mb,
        database_url=settings.database_url,
        url_cache_ttl_seconds=settings.explorer_url_cache_ttl_seconds,
        draft_cache_ttl_seconds=settings.explorer_draft_cache_ttl_seconds,
        draft_cache_namespace=(
            f"v3:{settings.explorer_draft_provider}:"
            f"{settings.explorer_source_draft_provider}:{settings.gemini_model}:"
            f"c{settings.explorer_source_chunk_characters}:"
            f"o{settings.explorer_source_max_output_tokens}"
        ),
    )


@lru_cache
def get_explorer_graph():
    settings = get_settings()
    client = get_llm_client() if settings.gemini_api_key else None
    return build_explorer_graph(compose_explorer_service(
        settings,
        client,
        get_explorer_synthesis_limiter(),
    ))


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
    external_place_search = None
    if settings.database_url and settings.google_maps_scraper_enabled:
        external_place_search = GoogleMapsPlaywrightSearch(
            build_draft_place_store(settings.database_url),
            timeout_seconds=settings.google_maps_scraper_timeout_seconds,
            max_alias_queries=settings.google_maps_scraper_max_alias_queries,
            max_concurrency=settings.google_maps_scraper_max_concurrency,
        )
    return create_root_graph(
        checkpointer=(None if settings.conversation_graph_checkpointer_enabled else False),
        information_finder_service=get_information_finder_service(),
        supervisor_service=create_supervisor_service(settings, shared_llm_client),
        explorer_service=compose_explorer_service(
            settings,
            shared_llm_client,
            get_explorer_synthesis_limiter(),
        ),
        place_checker_pipeline=(
            build_postgres_place_checker_pipeline(
                settings.database_url,
                external_place_search=external_place_search,
            )
            if settings.database_url
            else None
        ),
        itinerary_planner_graph=(
            build_valhalla_beam_first_itinerary_planner_graph(
                settings.valhalla_base_url,
                timeout_seconds=settings.valhalla_timeout_seconds,
                provider_version=settings.valhalla_graph_version,
                log_search_progress=settings.itinerary_log_search_progress,
            )
            if settings.route_provider == "valhalla"
            else None
        ),
        database_url=settings.database_url,
    )
