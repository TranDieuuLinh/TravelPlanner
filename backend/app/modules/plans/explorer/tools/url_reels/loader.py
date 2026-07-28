from __future__ import annotations

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from app.modules.plans.explorer.tools.url_reels.schema import UrlMetadata
from app.modules.plans.explorer.tools.url_reels.utils import QuietYtdlpLogger, canonicalize_url, detect_platform


class UrlReelLoader:
    def load_metadata(self, url: str) -> UrlMetadata:
        canonical_url = canonicalize_url(url)
        try:
            with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "logger": QuietYtdlpLogger()}) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except (DownloadError, ExtractorError) as exc:
            info = {"extractorError": str(exc)}
        if info is None:
            info = {}

        return UrlMetadata(
            originalUrl=url,
            canonicalUrl=canonical_url,
            platform=detect_platform(url),
            title=info.get("title"),
            description=info.get("description"),
            durationSeconds=info.get("duration"),
            thumbnailUrl=info.get("thumbnail"),
            uploader=info.get("uploader"),
            raw=info,
        )
