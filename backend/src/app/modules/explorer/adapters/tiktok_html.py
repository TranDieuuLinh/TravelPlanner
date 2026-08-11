import asyncio
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.ports import DownloadedMedia, UrlMediaClient


_EMBEDDED_DATA_RE = re.compile(
    r'<script(?=[^>]*\bid=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'])'
    r"[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_VIDEO_ID_RE = re.compile(r"/video/(\d+)")
_ALLOWED_MEDIA_SUFFIXES = (
    "akamaized.net",
    "byteicdn.com",
    "byteoversea.com",
    "ibytedtos.com",
    "tiktok.com",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
)


class FallbackUrlMediaClient:
    def __init__(self, primary: UrlMediaClient, fallback: UrlMediaClient) -> None:
        self.primary = primary
        self.fallback = fallback

    async def download(self, url: str, target_dir: str) -> DownloadedMedia:
        try:
            return await self.primary.download(url, target_dir)
        except Exception:
            return await self.fallback.download(url, target_dir)


class TikTokHtmlMediaClient:
    """Download public TikTok media from the JSON embedded in its Safari page."""

    def __init__(self, *, timeout_seconds: float = 30, max_filesize_mb: int = 120) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_filesize_mb * 1024 * 1024

    async def download(self, url: str, target_dir: str) -> DownloadedMedia:
        return await asyncio.to_thread(self._download_sync, url, target_dir)

    def _download_sync(self, url: str, target_dir: str) -> DownloadedMedia:
        from curl_cffi import requests

        canonical_url = urlparse(url)._replace(query="", fragment="").geturl()
        session = requests.Session(impersonate="safari")
        try:
            page = session.get(
                canonical_url,
                timeout=self.timeout_seconds,
                allow_redirects=True,
            )
            page.raise_for_status()
            if len(page.content) > 5 * 1024 * 1024:
                raise ExplorerOperationError(
                    "TIKTOK_HTML_TOO_LARGE", "Trang TikTok vượt giới hạn tải."
                )
            item = self._extract_item(page.text, canonical_url)
            media_url = self._media_url(item)
            target = Path(target_dir) / "media.mp4"
            self._stream_media(session, media_url, canonical_url, target)
            return DownloadedMedia(str(target), self._metadata(item))
        except ExplorerOperationError:
            raise
        except Exception as exc:
            raise ExplorerOperationError(
                "TIKTOK_HTML_DOWNLOAD_FAILED",
                "Không tải được video từ dữ liệu HTML TikTok.",
                retryable=True,
            ) from exc
        finally:
            session.close()

    @classmethod
    def _extract_item(cls, page_text: str, url: str) -> dict[str, Any]:
        match = _EMBEDDED_DATA_RE.search(page_text)
        if match is None:
            raise ExplorerOperationError(
                "TIKTOK_EMBEDDED_DATA_MISSING",
                "Trang TikTok không có dữ liệu video nhúng.",
                retryable=True,
            )
        try:
            data = json.loads(html.unescape(match.group(1)))
        except (TypeError, ValueError) as exc:
            raise ExplorerOperationError(
                "TIKTOK_EMBEDDED_DATA_INVALID", "Dữ liệu video TikTok không hợp lệ."
            ) from exc
        video_match = _VIDEO_ID_RE.search(urlparse(url).path)
        video_id = video_match.group(1) if video_match else None
        candidates: list[dict[str, Any]] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("video"), dict):
                    candidates.append(value)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(data)
        item = next(
            (value for value in candidates if str(value.get("id")) == video_id),
            candidates[0] if candidates else None,
        )
        if item is None:
            raise ExplorerOperationError(
                "TIKTOK_VIDEO_DATA_MISSING", "Không tìm thấy video trong trang TikTok."
            )
        return item

    @staticmethod
    def _media_url(item: dict[str, Any]) -> str:
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        candidates = [video.get("playAddr"), video.get("downloadAddr")]
        play_struct = video.get("PlayAddrStruct")
        if isinstance(play_struct, dict):
            url_list = play_struct.get("UrlList") or play_struct.get("urlList")
            if isinstance(url_list, list):
                candidates.extend(url_list)
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith("https://"):
                TikTokHtmlMediaClient._validate_media_url(candidate)
                return candidate
        raise ExplorerOperationError(
            "TIKTOK_MEDIA_URL_MISSING", "TikTok không cung cấp URL video công khai."
        )

    def _stream_media(self, session, media_url: str, referer: str, target: Path) -> None:
        current = media_url
        for _ in range(5):
            self._validate_media_url(current)
            response = session.get(
                current,
                headers={"Referer": referer},
                timeout=self.timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    break
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").casefold()
            if "video" not in content_type and "octet-stream" not in content_type:
                response.close()
                raise ExplorerOperationError(
                    "TIKTOK_MEDIA_INVALID", "TikTok không trả nội dung video."
                )
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > self.max_bytes:
                response.close()
                raise ExplorerOperationError(
                    "MEDIA_TOO_LARGE", "Video TikTok vượt giới hạn tải."
                )
            downloaded = 0
            with target.open("wb") as output:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    downloaded += len(chunk)
                    if downloaded > self.max_bytes:
                        response.close()
                        target.unlink(missing_ok=True)
                        raise ExplorerOperationError(
                            "MEDIA_TOO_LARGE", "Video TikTok vượt giới hạn tải."
                        )
                    output.write(chunk)
            response.close()
            if downloaded == 0:
                raise ExplorerOperationError(
                    "MEDIA_DOWNLOAD_EMPTY", "TikTok trả video rỗng."
                )
            return
        raise ExplorerOperationError(
            "TIKTOK_MEDIA_REDIRECT_LIMIT", "TikTok redirect video quá nhiều lần."
        )

    @staticmethod
    def _validate_media_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme != "https" or not any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in _ALLOWED_MEDIA_SUFFIXES
        ):
            raise ExplorerOperationError(
                "TIKTOK_MEDIA_HOST_BLOCKED", "TikTok trả media host không được phép."
            )

    @staticmethod
    def _metadata(item: dict[str, Any]) -> dict[str, Any]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        challenges = item.get("challenges") if isinstance(item.get("challenges"), list) else []
        tags = [
            value.get("title")
            for value in challenges
            if isinstance(value, dict) and isinstance(value.get("title"), str)
        ]
        description = str(item.get("desc") or "").strip()
        nickname = str(author.get("nickname") or author.get("uniqueId") or "").strip()
        return {
            "id": str(item.get("id") or ""),
            "title": f"TikTok by {nickname}" if nickname else "TikTok video",
            "description": description,
            "uploader": nickname or None,
            "duration": video.get("duration"),
            "location": item.get("locationCreated") or None,
            "tags": tags,
        }
