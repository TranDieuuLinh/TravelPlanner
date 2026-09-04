import asyncio

from app.modules.explorer.adapters import (
    CurlCffiWebsiteFetcher,
    GeminiAudioTranscriber,
    GeminiExplorerDraftGenerator,
    GeminiImageSourceExtractor,
    GeminiMediaAnalyzer,
    GeminiPrimaryEvidenceEvaluator,
    InlineImageSourceExtractor,
    InMemoryExplorerDraftCache,
    InMemoryExplorerSnapshotRepository,
    InMemoryImageOcrCache,
    InMemoryUrlSourceCache,
    PlaywrightWebsiteRenderer,
    PostgresExplorerDraftCache,
    PostgresUrlSourceCache,
    PythonYtDlpClient,
    PythonYtDlpMediaClient,
    RoutedExplorerDraftGenerator,
    NonSemanticExplorerFallback,
    TikTokHtmlMediaClient,
    UnconfiguredUrlSourceExtractor,
    UrlSourceRouter,
    WebsiteSourceExtractor,
    YouTubeTranscriptSourceExtractor,
    YtDlpAudioClient,
    YtDlpCaptionClient,
    YtDlpMetadataSourceExtractor,
    YtDlpSocialSourceExtractor,
    YamlInsightCatalog,
)
from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.api_output import to_explorer_api_output
from app.modules.explorer.contract import (
    ExplorerApiOutput,
    ExplorerBudget,
    ExplorerImageInput,
    ExplorerInput,
    ExplorerOutput,
    ExplorerPeople,
    ExplorerPlace,
    PlaceSource,
    RequestedItem,
    SourceNote,
)
from app.modules.explorer.graph import build_explorer_graph as _compile_explorer_graph
from app.modules.explorer.intake_patch import (
    BudgetPatch,
    CollectionOperation,
    IntegerScalarPatch,
    ItemCollectionPatch,
    PeoplePatch,
    PlaceCollectionPatch,
    ScalarOperation,
    StringCollectionPatch,
    StringScalarPatch,
    TripContextPatch,
    apply_trip_context_patch,
)
from app.modules.explorer.review import build_explorer_review
from app.modules.explorer.review_contract import (
    ExplorerReview,
    ExplorerReviewBudget,
    ExplorerReviewContext,
    ExplorerReviewKind,
)
from app.modules.explorer.ports import TagCatalog
from app.modules.explorer.place_dedupe import deduplicate_places
from app.modules.explorer.place_keys import place_name_key
from app.modules.explorer.service import ExplorerService
from app.modules.explorer.tools import normalize_budget_per_person
from app.shared.llm import LlmClient


def create_explorer_service(
    *,
    draft_provider: str = "gemini",
    source_draft_provider: str = "gemini",
    llm_client: LlmClient | None = None,
    image_llm_client: LlmClient | None = None,
    audio_llm_client: LlmClient | None = None,
    max_output_tokens: int = 4000,
    source_chunk_characters: int = 20_000,
    source_max_output_tokens: int = 8_000,
    source_max_concurrency: int = 5,
    synthesis_max_concurrency: int = 6,
    synthesis_limiter: asyncio.Semaphore | None = None,
    dedupe_provider: str = "gemini",
    note_provider: str = "gemini",
    url_timeout_seconds: float = 30,
    source_extraction_timeout_seconds: float = 90,
    source_synthesis_timeout_seconds: float = 105,
    source_chunk_timeout_seconds: float = 60,
    ytdlp_cookie_file: str | None = None,
    frame_interval_seconds: float = 3,
    frame_batch_size: int = 10,
    max_frames: int = 48,
    frame_max_concurrency: int = 5,
    audio_chunk_count: int = 3,
    audio_chunk_seconds: float = 60,
    youtube_audio_chunk_seconds: int = 300,
    youtube_audio_chunk_overlap_seconds: int = 5,
    youtube_audio_max_concurrency: int = 1,
    youtube_max_duration_seconds: int = 14_400,
    max_video_seconds: float = 180,
    max_media_mb: int = 120,
    database_url: str | None = None,
    url_cache_ttl_seconds: float = 604_800,
    draft_cache_ttl_seconds: float = 604_800,
    draft_cache_namespace: str = "explorer-draft-v1",
    tags_auto_path: str | None = None,
    insight_user_path: str | None = None,
) -> ExplorerService:
    tag_catalog = YamlTagCatalog(tags_auto_path)
    insight_catalog = YamlInsightCatalog(tag_catalog, insight_user_path)
    safe_fallback = NonSemanticExplorerFallback()
    gemini = None
    if llm_client is not None:
        gemini = GeminiExplorerDraftGenerator(
            llm_client,
            max_output_tokens=max_output_tokens,
            source_chunk_characters=source_chunk_characters,
            source_max_output_tokens=source_max_output_tokens,
            source_max_concurrency=source_max_concurrency,
            synthesis_max_concurrency=synthesis_max_concurrency,
            synthesis_limiter=synthesis_limiter,
            dedupe_provider=dedupe_provider,
            note_provider=note_provider,
            source_chunk_timeout_seconds=source_chunk_timeout_seconds,
            tag_catalog=tag_catalog,
        )
    if draft_provider != "gemini":
        raise ValueError(f"Unsupported Explorer draft provider: {draft_provider}")
    if source_draft_provider != "gemini":
        raise ValueError(
            f"Unsupported Explorer source draft provider: {source_draft_provider}"
        )
    if gemini is None:
        raise ValueError("Gemini Explorer requires an LlmClient.")
    if dedupe_provider not in {"rules", "gemini"}:
        raise ValueError(f"Unsupported Explorer dedupe provider: {dedupe_provider}")
    if note_provider not in {"rules", "gemini"}:
        raise ValueError(f"Unsupported Explorer note provider: {note_provider}")
    drafts = RoutedExplorerDraftGenerator(
        prompt_generator=gemini,
        source_generator=gemini,
    )
    metadata_client = PythonYtDlpClient(
        timeout_seconds=url_timeout_seconds,
        cookie_file=ytdlp_cookie_file,
    )
    website = WebsiteSourceExtractor(
        impersonated_fetcher=CurlCffiWebsiteFetcher(
            timeout_seconds=url_timeout_seconds
        ),
        renderer=PlaywrightWebsiteRenderer(timeout_seconds=url_timeout_seconds),
    )
    vision_client = image_llm_client or llm_client
    speech_client = audio_llm_client or llm_client or vision_client
    coverage_evaluator = (
        GeminiPrimaryEvidenceEvaluator(llm_client)
        if llm_client is not None
        else None
    )
    if vision_client is not None:
        analyzer = GeminiMediaAnalyzer(
            vision_client,
            audio_client=speech_client,
            frame_interval_seconds=frame_interval_seconds,
            frame_batch_size=frame_batch_size,
            max_frames=max_frames,
            frame_max_concurrency=frame_max_concurrency,
            audio_chunk_count=audio_chunk_count,
            audio_chunk_seconds=audio_chunk_seconds,
            max_video_seconds=max_video_seconds,
        )
        media_client = PythonYtDlpMediaClient(
            timeout_seconds=url_timeout_seconds,
            cookie_file=ytdlp_cookie_file,
            max_filesize_mb=max_media_mb,
            max_workers=4,
        )
        tiktok_client = TikTokHtmlMediaClient(
            timeout_seconds=url_timeout_seconds,
            max_filesize_mb=max_media_mb,
            max_workers=4,
        )
        tiktok = YtDlpSocialSourceExtractor(
            tiktok_client,
            analyzer,
            platform="TikTok",
            metadata_client=tiktok_client,
            coverage_evaluator=coverage_evaluator,
        )
        instagram = YtDlpSocialSourceExtractor(
            media_client,
            analyzer,
            platform="Instagram",
            metadata_client=metadata_client,
            coverage_evaluator=coverage_evaluator,
        )
        image_extractor = GeminiImageSourceExtractor(
            analyzer,
            cache=InMemoryImageOcrCache(),
        )
        youtube = YouTubeTranscriptSourceExtractor(
            YtDlpCaptionClient(
                timeout_seconds=url_timeout_seconds,
                cookie_file=ytdlp_cookie_file,
            ),
            YtDlpAudioClient(
                timeout_seconds=url_timeout_seconds,
                cookie_file=ytdlp_cookie_file,
                max_filesize_mb=max_media_mb,
            ),
            GeminiAudioTranscriber(
                speech_client,
                chunk_seconds=youtube_audio_chunk_seconds,
                overlap_seconds=youtube_audio_chunk_overlap_seconds,
                max_concurrency=youtube_audio_max_concurrency,
                max_duration_seconds=youtube_max_duration_seconds,
            ),
            coverage_evaluator=coverage_evaluator,
            media_client=media_client,
            analyzer=analyzer,
        )
    else:
        youtube = YtDlpMetadataSourceExtractor(metadata_client, platform="YouTube")
        tiktok = YtDlpMetadataSourceExtractor(metadata_client, platform="TikTok")
        instagram = YtDlpMetadataSourceExtractor(metadata_client, platform="Instagram")
        image_extractor = InlineImageSourceExtractor()
    url_cache = (
        PostgresUrlSourceCache(database_url, ttl_seconds=url_cache_ttl_seconds)
        if database_url
        else InMemoryUrlSourceCache()
    )
    draft_cache = (
        PostgresExplorerDraftCache(
            database_url,
            namespace=draft_cache_namespace,
            ttl_seconds=draft_cache_ttl_seconds,
        )
        if database_url
        else InMemoryExplorerDraftCache()
    )
    return ExplorerService(
        drafts=drafts,
        url_extractor=UrlSourceRouter(
            youtube=youtube,
            tiktok=tiktok,
            instagram=instagram,
            website=website,
        ),
        image_extractor=image_extractor,
        snapshots=InMemoryExplorerSnapshotRepository(),
        url_cache=url_cache,
        draft_cache=draft_cache,
        draft_cache_namespace=draft_cache_namespace,
        source_extraction_timeout_seconds=source_extraction_timeout_seconds,
        source_synthesis_timeout_seconds=source_synthesis_timeout_seconds,
        fallback_drafts=safe_fallback,
        tag_catalog=tag_catalog,
        insight_catalog=insight_catalog,
    )


def _create_development_explorer_service() -> ExplorerService:
    tag_catalog = YamlTagCatalog()
    insight_catalog = YamlInsightCatalog(tag_catalog)
    drafts = NonSemanticExplorerFallback()
    return ExplorerService(
        drafts=drafts,
        url_extractor=UnconfiguredUrlSourceExtractor(),
        image_extractor=InlineImageSourceExtractor(),
        snapshots=InMemoryExplorerSnapshotRepository(),
        tag_catalog=tag_catalog,
        insight_catalog=insight_catalog,
    )


def build_explorer_graph(service: ExplorerService | None = None):
    """Compile the Explorer subgraph; composition stays at the public boundary."""
    return _compile_explorer_graph(service or _create_development_explorer_service())


__all__ = [
    "ExplorerApiOutput",
    "BudgetPatch",
    "CollectionOperation",
    "ExplorerBudget",
    "ExplorerImageInput",
    "ExplorerInput",
    "ExplorerOutput",
    "ExplorerPeople",
    "ExplorerPlace",
    "ExplorerReview",
    "ExplorerReviewBudget",
    "ExplorerReviewContext",
    "ExplorerReviewKind",
    "PlaceSource",
    "IntegerScalarPatch",
    "ItemCollectionPatch",
    "PeoplePatch",
    "PlaceCollectionPatch",
    "RequestedItem",
    "SourceNote",
    "ScalarOperation",
    "StringCollectionPatch",
    "StringScalarPatch",
    "TripContextPatch",
    "TagCatalog",
    "YamlTagCatalog",
    "YamlInsightCatalog",
    "build_explorer_graph",
    "build_explorer_review",
    "create_explorer_service",
    "to_explorer_api_output",
    "apply_trip_context_patch",
    "deduplicate_places",
    "normalize_budget_per_person",
    "place_name_key",
]
