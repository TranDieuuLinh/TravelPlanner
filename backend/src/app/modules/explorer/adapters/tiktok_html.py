import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
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
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$")
_ALLOWED_MEDIA_SUFFIXES = (
    "akamaized.net",
    "byteicdn.com",
    "byteoversea.com",
    "ibytedtos.com",
    "tiktok.com",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
)


class _RangeUnsupported(Exception):
    """Signal that the media server cannot serve the requested byte range."""


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
    """Read metadata and download media from TikTok's embedded Safari JSON."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        max_filesize_mb: int = 120,
        max_workers: int = 4,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_filesize_mb * 1024 * 1024
        self.max_workers = max_workers
        self._session_factory = session_factory

    async def download(self, url: str, target_dir: str) -> DownloadedMedia:
        return await asyncio.to_thread(self._download_sync, url, target_dir)

    async def extract(self, url: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._extract_metadata_sync, url)

    def _extract_metadata_sync(self, url: str) -> dict[str, Any]:
        canonical_url = urlparse(url)._replace(query="", fragment="").geturl()
        session = self._new_session()
        try:
            return self._metadata(self._load_item(session, canonical_url))
        except ExplorerOperationError:
            raise
        except Exception as exc:
            raise ExplorerOperationError(
                "TIKTOK_HTML_METADATA_FAILED",
                "Không đọc được metadata TikTok từ dữ liệu HTML.",
                retryable=True,
            ) from exc
        finally:
            session.close()

    def _download_sync(self, url: str, target_dir: str) -> DownloadedMedia:
        canonical_url = urlparse(url)._replace(query="", fragment="").geturl()
        session = self._new_session()
        try:
            item = self._load_item(session, canonical_url)
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

    def _load_item(self, session, canonical_url: str) -> dict[str, Any]:
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
        return self._extract_item(page.text, canonical_url)

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
        probe = self._open_media_response(
            session, media_url, referer, range_header="bytes=0-0"
        )
        try:
            total_size = self._range_total_size(probe)
            if total_size is not None:
                if total_size > self.max_bytes:
                    raise ExplorerOperationError(
                        "MEDIA_TOO_LARGE", "Video TikTok vượt giới hạn tải."
                    )
                probe.close()
                try:
                    self._download_ranges(media_url, referer, target, total_size)
                    return
                except _RangeUnsupported:
                    pass
            else:
                probe.raise_for_status()
        finally:
            probe.close()

        self._download_sequential(session, media_url, referer, target)

    def _download_sequential(
        self, session, media_url: str, referer: str, target: Path
    ) -> None:
        response = self._open_media_response(session, media_url, referer)
        try:
            response.raise_for_status()
            self._validate_video_response(response)
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > self.max_bytes:
                raise ExplorerOperationError(
                    "MEDIA_TOO_LARGE", "Video TikTok vượt giới hạn tải."
                )
            downloaded = 0
            with target.open("wb") as output:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    downloaded += len(chunk)
                    if downloaded > self.max_bytes:
                        raise ExplorerOperationError(
                            "MEDIA_TOO_LARGE", "Video TikTok vượt giới hạn tải."
                        )
                    output.write(chunk)
            if downloaded == 0:
                raise ExplorerOperationError(
                    "MEDIA_DOWNLOAD_EMPTY", "TikTok trả video rỗng."
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            response.close()

    def _download_ranges(
        self, media_url: str, referer: str, target: Path, total_size: int
    ) -> None:
        ranges = self._split_ranges(total_size, self.max_workers)
        parts = [target.with_name(f"{target.name}.part-{index}") for index in range(len(ranges))]

        def download_part(index: int) -> None:
            start, end = ranges[index]
            worker_session = self._new_session()
            response = self._open_media_response(
                worker_session,
                media_url,
                referer,
                range_header=f"bytes={start}-{end}",
            )
            try:
                if response.status_code != 206:
                    raise _RangeUnsupported()
                content_range = self._parse_content_range(
                    response.headers.get("content-range", "")
                )
                if content_range != (start, end, total_size):
                    raise _RangeUnsupported()
                self._validate_video_response(response)
                expected = end - start + 1
                content_length = int(response.headers.get("content-length") or 0)
                if content_length and content_length != expected:
                    raise _RangeUnsupported()
                written = 0
                with parts[index].open("wb") as output:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        written += len(chunk)
                        output.write(chunk)
                if written != expected:
                    raise ExplorerOperationError(
                        "MEDIA_DOWNLOAD_INCOMPLETE", "TikTok trả thiếu một phần video."
                    )
            finally:
                response.close()
                worker_session.close()

        try:
            with ThreadPoolExecutor(max_workers=len(ranges)) as executor:
                futures = [executor.submit(download_part, index) for index in range(len(ranges))]
                for future in futures:
                    future.result()
            with target.open("wb") as output:
                for part in parts:
                    with part.open("rb") as chunk:
                        while data := chunk.read(256 * 1024):
                            output.write(data)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            for part in parts:
                part.unlink(missing_ok=True)

    def _open_media_response(
        self, session, media_url: str, referer: str, range_header: str | None = None
    ):
        current = media_url
        headers = {"Referer": referer}
        if range_header:
            headers["Range"] = range_header
        for _ in range(5):
            self._validate_media_url(current)
            response = session.get(
                current,
                headers=headers,
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
            return response
        raise ExplorerOperationError(
            "TIKTOK_MEDIA_REDIRECT_LIMIT", "TikTok redirect video quá nhiều lần."
        )

    def _new_session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from curl_cffi import requests

        return requests.Session(impersonate="safari")

    @staticmethod
    def _split_ranges(total_size: int, worker_count: int) -> list[tuple[int, int]]:
        actual_workers = min(total_size, worker_count)
        chunk_size = (total_size + actual_workers - 1) // actual_workers
        return [
            (start, min(total_size - 1, start + chunk_size - 1))
            for start in range(0, total_size, chunk_size)
        ]

    @classmethod
    def _range_total_size(cls, response) -> int | None:
        if response.status_code != 206:
            return None
        parsed = cls._parse_content_range(response.headers.get("content-range", ""))
        if parsed is None:
            return None
        start, end, total_size = parsed
        if start != 0 or end != 0 or total_size <= 0:
            return None
        return total_size

    @staticmethod
    def _parse_content_range(value: str) -> tuple[int, int, int] | None:
        match = _CONTENT_RANGE_RE.match(value.strip())
        if not match or match.group(3) == "*":
            return None
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    @staticmethod
    def _validate_video_response(response) -> None:
        content_type = response.headers.get("content-type", "").casefold()
        if "video" not in content_type and "octet-stream" not in content_type:
            raise ExplorerOperationError(
                "TIKTOK_MEDIA_INVALID", "TikTok không trả nội dung video."
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
