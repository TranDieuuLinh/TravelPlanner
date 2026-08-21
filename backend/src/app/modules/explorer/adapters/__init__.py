from app.modules.explorer.adapters.development import (
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    NonSemanticExplorerFallback,
    UnconfiguredUrlSourceExtractor,
)
from app.modules.explorer.adapters.draft_cache import (
    InMemoryExplorerDraftCache,
    PostgresExplorerDraftCache,
)
from app.modules.explorer.adapters.source_extraction_cache import (
    InMemorySourceExtractionCache,
    PostgresSourceExtractionCache,
)
from app.modules.explorer.adapters.draft_routing import RoutedExplorerDraftGenerator
from app.modules.explorer.adapters.gemini import GeminiExplorerDraftGenerator
from app.modules.explorer.adapters.image_source import GeminiImageSourceExtractor
from app.modules.explorer.adapters.image_cache import InMemoryImageOcrCache
from app.modules.explorer.adapters.media_analysis import GeminiMediaAnalyzer
from app.modules.explorer.adapters.primary_coverage import (
    GeminiPrimaryEvidenceEvaluator,
)
from app.modules.explorer.adapters.tiktok_html import (
    FallbackUrlMediaClient,
    TikTokHtmlMediaClient,
)
from app.modules.explorer.adapters.url_cache import (
    InMemoryUrlSourceCache,
    PostgresUrlSourceCache,
)
from app.modules.explorer.adapters.website_render import PlaywrightWebsiteRenderer
from app.modules.explorer.adapters.website_fetch import CurlCffiWebsiteFetcher
from app.modules.explorer.adapters.url_sources import (
    PythonYtDlpClient,
    PythonYtDlpMediaClient,
    UrlSourceRouter,
    WebsiteSourceExtractor,
    YtDlpMetadataSourceExtractor,
    YtDlpSocialSourceExtractor,
)
from app.modules.explorer.adapters.youtube_transcript import (
    GeminiAudioTranscriber,
    YtDlpAudioClient,
    YtDlpCaptionClient,
)
from app.modules.explorer.adapters.youtube_source import (
    YouTubeTranscriptSourceExtractor,
)
from app.modules.explorer.adapters.user_insights import YamlInsightCatalog
__all__ = [
    "GeminiExplorerDraftGenerator",
    "CurlCffiWebsiteFetcher",
    "GeminiImageSourceExtractor",
    "InMemoryImageOcrCache",
    "GeminiMediaAnalyzer",
    "GeminiPrimaryEvidenceEvaluator",
    "InMemoryExplorerSnapshotRepository",
    "InMemoryExplorerDraftCache",
    "InMemorySourceExtractionCache",
    "InMemoryUrlSourceCache",
    "InlineImageSourceExtractor",
    "FallbackUrlMediaClient",
    "PythonYtDlpClient",
    "PythonYtDlpMediaClient",
    "PlaywrightWebsiteRenderer",
    "PostgresUrlSourceCache",
    "PostgresExplorerDraftCache",
    "PostgresSourceExtractionCache",
    "NonSemanticExplorerFallback",
    "RoutedExplorerDraftGenerator",
    "TikTokHtmlMediaClient",
    "UnconfiguredUrlSourceExtractor",
    "UrlSourceRouter",
    "WebsiteSourceExtractor",
    "YtDlpMetadataSourceExtractor",
    "YtDlpSocialSourceExtractor",
    "GeminiAudioTranscriber",
    "YouTubeTranscriptSourceExtractor",
    "YtDlpAudioClient",
    "YtDlpCaptionClient",
    "YamlInsightCatalog",
]
