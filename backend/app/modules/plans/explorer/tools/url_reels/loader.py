from __future__ import annotations

from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import (
    DownloadError,
    ExtractorError,
    UnsupportedError,
    YoutubeDLError,
)

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import UrlMetadata
from app.modules.plans.explorer.tools.url_reels.utils import (
    QuietYtdlpLogger,
    canonicalize_url,
    detect_platform,
)


class UrlReelLoader:
    def load_metadata(self, url: str) -> UrlMetadata:
        canonical_url = canonicalize_url(url)
        base_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "logger": QuietYtdlpLogger(),
            "socket_timeout": settings.url_reel_network_timeout_seconds,
            "retries": 1,
            "extractor_retries": 1,
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
                "impersonate": ImpersonateTarget.from_str("chrome-131:android-14"),
            },
        ):
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        canonical_url,
                        download=False,
                    )
                break
            except (DownloadError, ExtractorError, YoutubeDLError) as exc:
                failures.append(exc)
        if info is None and failures:
            info = {"extractorError": str(failures[-1])}
        if info is None:
            info = {}

        return _metadata_from_info(url, canonical_url, info)

    def load_source(
        self,
        url: str,
        *,
        work_dir: Path,
    ) -> tuple[UrlMetadata, Path]:
        """Download one public reel and reuse the same yt-dlp info as metadata."""

        canonical_url = canonicalize_url(url)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(work_dir / "reel_source.%(ext)s")
        base_options = {
            "format": "worst[ext=mp4]/worst",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietYtdlpLogger(),
            "socket_timeout": settings.url_reel_network_timeout_seconds,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_retries": 1,
        }
        failures: list[Exception] = []
        for options in (
            base_options,
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str("chrome"),
            },
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str("chrome-131:android-14"),
            },
        ):
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(canonical_url, download=True)
                    prepared_path = Path(ydl.prepare_filename(info))
                video_path = _downloaded_path(
                    info,
                    prepared_path=prepared_path,
                    work_dir=work_dir,
                )
                if video_path is None:
                    raise DownloadError("yt-dlp did not create a video file")
                return (
                    _metadata_from_info(url, canonical_url, info),
                    video_path,
                )
            except (
                DownloadError,
                ExtractorError,
                UnsupportedError,
                YoutubeDLError,
            ) as exc:
                failures.append(exc)
                for partial in work_dir.glob("reel_source.*"):
                    partial.unlink(missing_ok=True)
        raise DownloadError(
            "yt-dlp failed to fetch reel metadata and media"
        ) from failures[-1]


def _metadata_from_info(
    url: str,
    canonical_url: str,
    info: dict,
) -> UrlMetadata:
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
            key: _normalized_metadata_value(key, info[key])
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
                "chapters",
                "tags",
                "categories",
                "extractorError",
            )
            if info.get(key) is not None
        },
    )


def _downloaded_path(
    info: dict,
    *,
    prepared_path: Path,
    work_dir: Path,
) -> Path | None:
    requested_downloads = info.get("requested_downloads")
    if isinstance(requested_downloads, list):
        for download in requested_downloads:
            if not isinstance(download, dict):
                continue
            filepath = download.get("filepath")
            if filepath and Path(filepath).is_file():
                return Path(filepath)
    if prepared_path.is_file():
        return prepared_path
    return next(
        (
            path
            for path in sorted(work_dir.glob("reel_source.*"))
            if path.is_file() and path.stat().st_size > 0
        ),
        None,
    )


def _normalized_metadata_value(key: str, value: object) -> object:
    """Keep only compact, extraction-relevant metadata from yt-dlp."""
    if key == "chapters" and isinstance(value, list):
        return [
            {
                "title": str(chapter.get("title", "")).strip(),
                "startTime": chapter.get("start_time"),
                "endTime": chapter.get("end_time"),
            }
            for chapter in value[:100]
            if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
        ]
    if key in {"tags", "categories"} and isinstance(value, list):
        return [str(item).strip() for item in value[:100] if str(item).strip()]
    return value
