from app.modules.explorer.contract import (
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
from app.modules.explorer.adapters import (
    CurlCffiWebsiteFetcher,
    FallbackUrlMediaClient,
    GeminiExplorerDraftGenerator,
    GeminiImageSourceExtractor,
    GeminiMediaAnalyzer,
    InMemoryExplorerDraftCache,
    InMemoryExplorerSnapshotRepository,
    InMemoryUrlSourceCache,
    InlineImageSourceExtractor,
    PythonYtDlpClient,
    PythonYtDlpMediaClient,
    PlaywrightWebsiteRenderer,
    PostgresUrlSourceCache,
    PostgresExplorerDraftCache,
    RuleBasedExplorerDraftGenerator,
    RoutedExplorerDraftGenerator,
    TikTokHtmlMediaClient,
    UnconfiguredUrlSourceExtractor,
    UrlSourceRouter,
    WebsiteSourceExtractor,
    YtDlpMetadataSourceExtractor,
    YtDlpSocialSourceExtractor,
)
from app.modules.explorer.graph import build_explorer_graph as _compile_explorer_graph
from app.modules.explorer.service import ExplorerService
from app.shared.llm import LlmClient


def create_explorer_service(
    *,
    draft_provider: str = "rules",
    llm_client: LlmClient | None = None,
    image_llm_client: LlmClient | None = None,
    audio_llm_client: LlmClient | None = None,
    max_output_tokens: int = 4000,
    url_timeout_seconds: float = 30,
    ytdlp_cookie_file: str | None = None,
    frame_interval_seconds: float = 1.5,
    frame_batch_size: int = 10,
    max_frames: int = 72,
    frame_max_concurrency: int = 5,
    audio_chunk_count: int = 3,
    max_video_seconds: float = 180,
    max_media_mb: int = 120,
    database_url: str | None = None,
    url_cache_ttl_seconds: float = 604_800,
    draft_cache_ttl_seconds: float = 604_800,
    draft_cache_namespace: str = "explorer-draft-v1",
) -> ExplorerService:
    rules = RuleBasedExplorerDraftGenerator()
    gemini = None
    if llm_client is not None:
        gemini = GeminiExplorerDraftGenerator(
            llm_client, max_output_tokens=max_output_tokens
        )
    if draft_provider == "gemini":
        if gemini is None:
            raise ValueError("Gemini Explorer requires an LlmClient.")
        prompt_generator = gemini
    elif draft_provider == "rules":
        prompt_generator = rules
    else:
        raise ValueError(f"Unsupported Explorer draft provider: {draft_provider}")
    drafts = RoutedExplorerDraftGenerator(
        prompt_generator=prompt_generator,
        source_generator=gemini or rules,
    )
    metadata_client = PythonYtDlpClient(
        timeout_seconds=url_timeout_seconds,
        cookie_file=ytdlp_cookie_file,
    )
    youtube = YtDlpMetadataSourceExtractor(metadata_client, platform="YouTube")
    website = WebsiteSourceExtractor(
        timeout_seconds=url_timeout_seconds,
        impersonated_fetcher=CurlCffiWebsiteFetcher(
            timeout_seconds=url_timeout_seconds
        ),
        renderer=PlaywrightWebsiteRenderer(timeout_seconds=url_timeout_seconds),
    )
    vision_client = image_llm_client or llm_client
    speech_client = audio_llm_client or llm_client or vision_client
    if vision_client is not None:
        analyzer = GeminiMediaAnalyzer(
            vision_client,
            audio_client=speech_client,
            frame_interval_seconds=frame_interval_seconds,
            frame_batch_size=frame_batch_size,
            max_frames=max_frames,
            frame_max_concurrency=frame_max_concurrency,
            audio_chunk_count=audio_chunk_count,
            max_video_seconds=max_video_seconds,
        )
        media_client = PythonYtDlpMediaClient(
            timeout_seconds=url_timeout_seconds,
            cookie_file=ytdlp_cookie_file,
            max_filesize_mb=max_media_mb,
        )
        tiktok = YtDlpSocialSourceExtractor(
            FallbackUrlMediaClient(
                TikTokHtmlMediaClient(
                    timeout_seconds=url_timeout_seconds,
                    max_filesize_mb=max_media_mb,
                ),
                media_client,
            ),
            analyzer,
            platform="TikTok",
        )
        instagram = YtDlpSocialSourceExtractor(
            media_client, analyzer, platform="Instagram"
        )
        image_extractor = GeminiImageSourceExtractor(analyzer)
    else:
        tiktok = YtDlpMetadataSourceExtractor(metadata_client, platform="TikTok")
        instagram = YtDlpMetadataSourceExtractor(metadata_client, platform="Instagram")
        image_extractor = InlineImageSourceExtractor(rules)
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
    )


def _create_development_explorer_service() -> ExplorerService:
    drafts = RuleBasedExplorerDraftGenerator()
    return ExplorerService(
        drafts=drafts,
        url_extractor=UnconfiguredUrlSourceExtractor(),
        image_extractor=InlineImageSourceExtractor(drafts),
        snapshots=InMemoryExplorerSnapshotRepository(),
    )


def build_explorer_graph(service: ExplorerService | None = None):
    """Compile the Explorer subgraph; composition stays at the public boundary."""
    return _compile_explorer_graph(service or _create_development_explorer_service())


__all__ = [
    "ExplorerBudget", "ExplorerImageInput", "ExplorerInput", "ExplorerOutput",
    "ExplorerPeople", "ExplorerPlace", "PlaceSource", "RequestedItem", "SourceNote",
    "build_explorer_graph",
    "create_explorer_service",
]
