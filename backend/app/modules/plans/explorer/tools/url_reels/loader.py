from __future__ import annotations

from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError, ExtractorError

from app.modules.plans.explorer.tools.url_reels.schema import UrlMetadata
from app.modules.plans.explorer.tools.url_reels.utils import QuietYtdlpLogger, canonicalize_url, detect_platform


class UrlReelLoader:
    def load_metadata(self, url: str) -> UrlMetadata:
        canonical_url = canonicalize_url(url)
        base_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "logger": QuietYtdlpLogger(),
        }
        info = None
        failures: list[Exception] = []
        for options in (
            base_options,
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str("chrome"),
            },
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str(
                    "chrome-131:android-14"
                ),
            },
        ):
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        canonical_url,
                        download=False,
                    )
                break
            except (DownloadError, ExtractorError) as exc:
                failures.append(exc)
        if info is None and failures:
            info = {"extractorError": str(failures[-1])}
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
            raw={
                key: info[key]
                for key in (
                    "address",
                    "street_address",
                    "location",
                    "location_name",
                    "location_address",
                    "venue",
                    "place",
                    "city",
                    "locality",
                    "region",
                    "state",
                    "province",
                    "country",
                    "extractorError",
                )
                if info.get(key) is not None
            },
        )
