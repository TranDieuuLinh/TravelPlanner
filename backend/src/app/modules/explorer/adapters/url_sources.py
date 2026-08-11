import asyncio
import ipaddress
import socket
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult
from app.modules.explorer.ports import (
    DownloadedMedia,
    MediaAnalyzer,
    UrlMediaClient,
    UrlMetadataClient,
    WebsiteFetcher,
    WebsiteRenderer,
)


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
_SOCIAL_HOSTS = _TIKTOK_HOSTS | _INSTAGRAM_HOSTS
_SOCIAL_IMPERSONATION_TARGETS: tuple[str | None, ...] = (
    None,
    "chrome",
    "chrome-131:android-14",
)
_SMALL_MUXED_MP4_FORMAT = "worst[ext=mp4]/worst"


def _ytdlp_extract(
    url: str,
    options: dict[str, Any],
    *,
    download: bool,
) -> dict[str, Any]:
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget

    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host in _SOCIAL_HOSTS:
        url = parsed._replace(query="", fragment="").geturl()
    targets: tuple[str | None, ...] = (
        _SOCIAL_IMPERSONATION_TARGETS if host in _SOCIAL_HOSTS else (None,)
    )
    last_error: Exception | None = None
    for target in targets:
        attempt_options = dict(options)
        if target is not None:
            attempt_options["impersonate"] = ImpersonateTarget.from_str(target)
        try:
            with yt_dlp.YoutubeDL(attempt_options) as downloader:
                info = downloader.extract_info(url, download=download)
                return downloader.sanitize_info(info)
        except yt_dlp.utils.YoutubeDLError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ExplorerOperationError("URL_DOWNLOAD_FAILED", "yt-dlp không xử lý URL.")


class PythonYtDlpClient:
    """Metadata-only yt-dlp adapter used by YouTube and no-Gemini fallback."""

    def __init__(self, *, timeout_seconds: float = 30, cookie_file: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_file = cookie_file

    async def extract(self, url: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._extract_sync, url)

    def _extract_sync(self, url: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": self.timeout_seconds,
            "retries": 1,
            "extractor_retries": 1,
        }
        if self.cookie_file:
            options["cookiefile"] = self.cookie_file
        return _ytdlp_extract(url, options, download=False)


class PythonYtDlpMediaClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        cookie_file: str | None = None,
        max_filesize_mb: int = 120,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_file = cookie_file
        self.max_filesize_mb = max_filesize_mb

    async def download(self, url: str, target_dir: str) -> DownloadedMedia:
        return await asyncio.to_thread(self._download_sync, url, target_dir)

    def _download_sync(self, url: str, target_dir: str) -> DownloadedMedia:
        options: dict[str, Any] = {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": _SMALL_MUXED_MP4_FORMAT,
            "outtmpl": str(Path(target_dir) / "media.%(ext)s"),
            "socket_timeout": self.timeout_seconds,
            "max_filesize": self.max_filesize_mb * 1024 * 1024,
            "retries": 1,
            "extractor_retries": 1,
            "fragment_retries": 1,
        }
        if self.cookie_file:
            options["cookiefile"] = self.cookie_file
        metadata = _ytdlp_extract(url, options, download=True)
        candidates = [
            path for path in Path(target_dir).glob("media.*")
            if path.is_file() and not path.name.endswith((".part", ".ytdl"))
        ]
        if not candidates:
            raise ExplorerOperationError(
                "MEDIA_DOWNLOAD_EMPTY", "yt-dlp không tạo media file."
            )
        return DownloadedMedia(str(max(candidates, key=lambda path: path.stat().st_size)), metadata)


class YtDlpMetadataSourceExtractor:
    def __init__(self, client: UrlMetadataClient, *, platform: str) -> None:
        self.client = client
        self.platform = platform

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        try:
            metadata = await self.client.extract(url)
        except Exception as exc:
            raise ExplorerOperationError(
                "URL_METADATA_FAILED",
                f"Không đọc được metadata {self.platform}.",
                retryable=True,
            ) from exc
        artifacts = metadata_artifacts(metadata, url)
        if not artifacts:
            raise ExplorerOperationError(
                "URL_EVIDENCE_EMPTY", f"{self.platform} không có caption/metadata hữu ích."
            )
        return SourceExtractionResult(
            sourceIndex=source_index, sourceKind="url", sourceRef=url,
            status="succeeded", artifacts=artifacts,
        )


class YtDlpSocialSourceExtractor:
    def __init__(
        self,
        client: UrlMediaClient,
        analyzer: MediaAnalyzer,
        *,
        platform: str,
    ) -> None:
        self.client = client
        self.analyzer = analyzer
        self.platform = platform

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        with TemporaryDirectory(prefix="explorer-media-") as work_dir:
            try:
                downloaded = await self.client.download(url, work_dir)
            except Exception as exc:
                raise ExplorerOperationError(
                    "URL_DOWNLOAD_FAILED",
                    f"Không tải được media {self.platform}.",
                    retryable=True,
                ) from exc
            artifacts = metadata_artifacts(downloaded.metadata, url)
            analysis = await self.analyzer.analyze(
                downloaded.file_path, work_dir, url
            )
            artifacts.extend(analysis.artifacts)
        if not artifacts:
            if analysis.failures:
                first_error = analysis.failures[0].error
                raise ExplorerOperationError(
                    first_error.code,
                    first_error.message,
                    retryable=first_error.retryable,
                )
            raise ExplorerOperationError(
                "URL_EVIDENCE_EMPTY", f"{self.platform} không có evidence hữu ích."
            )
        return SourceExtractionResult(
            sourceIndex=source_index, sourceKind="url", sourceRef=url,
            status="partial" if analysis.failures else "succeeded",
            artifacts=artifacts,
            branchFailures=analysis.failures,
        )


class WebsiteSourceExtractor:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20,
        max_bytes: int = 5_000_000,
        impersonated_fetcher: WebsiteFetcher | None = None,
        renderer: WebsiteRenderer | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.impersonated_fetcher = impersonated_fetcher
        self.renderer = renderer

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        try:
            html, final_url = await self._download(url)
        except ExplorerOperationError as exc:
            if exc.code not in {
                "WEB_DOWNLOAD_FAILED", "WEB_REDIRECT_LIMIT"
            }:
                raise
            html, final_url = await self._fallback_download(url, exc)
        markdown = await self._markdown(html, final_url)
        if (not markdown or not markdown.strip()) and self.renderer is not None:
            html, final_url = await self.renderer.render(url)
            markdown = await self._markdown(html, final_url)
        if not markdown or not markdown.strip():
            raise ExplorerOperationError(
                "WEB_TEXT_EMPTY", "Website không có nội dung chính để trích xuất."
            )
        artifact = SourceArtifact(
            artifactType="web_text", text=markdown[:60_000],
            sourceUrl=final_url, observedAt=datetime.now(UTC).isoformat(),
        )
        return SourceExtractionResult(
            sourceIndex=source_index, sourceKind="url", sourceRef=url,
            status="succeeded", artifacts=[artifact],
        )

    async def _fallback_download(
        self, url: str, original_error: ExplorerOperationError
    ) -> tuple[str, str]:
        if self.impersonated_fetcher is not None:
            try:
                return await self.impersonated_fetcher.fetch(url)
            except ExplorerOperationError:
                if self.renderer is None:
                    raise
        if self.renderer is not None:
            return await self.renderer.render(url)
        raise original_error

    @staticmethod
    async def _markdown(html: str, final_url: str) -> str | None:
        return await asyncio.to_thread(
            trafilatura.extract,
            html,
            url=final_url,
            output_format="markdown",
            include_links=True,
            include_images=False,
            favor_recall=True,
        )

    async def _download(self, url: str) -> tuple[str, str]:
        current = url
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={
                "user-agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            follow_redirects=False,
        ) as client:
            for _ in range(4):
                await self._validate_public_url(current)
                try:
                    response = await client.get(current)
                except httpx.HTTPError as exc:
                    raise ExplorerOperationError(
                        "WEB_DOWNLOAD_FAILED", "Không tải được website.", retryable=True
                    ) from exc
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise ExplorerOperationError(
                        "WEB_DOWNLOAD_FAILED",
                        f"Website trả HTTP {response.status_code}.",
                        retryable=response.status_code >= 500,
                    )
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    raise ExplorerOperationError(
                        "WEB_CONTENT_UNSUPPORTED", "URL không trả nội dung HTML."
                    )
                if len(response.content) > self.max_bytes:
                    raise ExplorerOperationError(
                        "WEB_CONTENT_TOO_LARGE", "Website vượt giới hạn tải."
                    )
                return response.text, str(response.url)
        raise ExplorerOperationError("WEB_REDIRECT_LIMIT", "Website redirect quá nhiều lần.")

    @staticmethod
    async def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            raise ExplorerOperationError("UNSUPPORTED_URL", "Website URL không hợp lệ.")
        try:
            records = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except socket.gaierror as exc:
            raise ExplorerOperationError(
                "WEB_DNS_FAILED", "Không phân giải được website.", retryable=True
            ) from exc
        for record in records:
            address = ipaddress.ip_address(record[4][0])
            if not address.is_global:
                raise ExplorerOperationError(
                    "WEB_PRIVATE_ADDRESS", "Website trỏ đến địa chỉ nội bộ bị chặn."
                )


class UrlSourceRouter:
    def __init__(self, *, youtube, tiktok, instagram, website) -> None:
        self.youtube = youtube
        self.tiktok = tiktok
        self.instagram = instagram
        self.website = website

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        host = (urlparse(url).hostname or "").casefold().rstrip(".")
        if host in _YOUTUBE_HOSTS:
            extractor = self.youtube
        elif host in _TIKTOK_HOSTS:
            extractor = self.tiktok
        elif host in _INSTAGRAM_HOSTS:
            extractor = self.instagram
        else:
            extractor = self.website
        return await extractor.extract(
            url, source_index=source_index, raw_prompt=raw_prompt
        )


def metadata_artifacts(metadata: dict[str, Any], url: str) -> list[SourceArtifact]:
    observed_at = datetime.now(UTC).isoformat()
    artifacts = []
    for field, artifact_type in (
        ("title", "url_metadata"),
        ("description", "caption"),
        ("location", "url_metadata"),
    ):
        value = metadata.get(field)
        if isinstance(value, str) and value.strip():
            artifacts.append(SourceArtifact(
                artifactType=artifact_type, text=value.strip()[:60_000],
                sourceUrl=url, observedAt=observed_at,
            ))
    tags = metadata.get("tags")
    if isinstance(tags, list) and tags:
        text = ", ".join(str(tag).strip() for tag in tags[:30] if str(tag).strip())
        if text:
            artifacts.append(SourceArtifact(
                artifactType="url_metadata", text=text,
                sourceUrl=url, observedAt=observed_at,
            ))
    return artifacts
