from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.caption_structurer import (
    CaptionStructurer,
)
from app.modules.plans.explorer.tools.url_reels.extractor import (
    UrlReelContextExtractor,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.utils import canonicalize_url
from app.shared.errors import AppError


_ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class WebPageDocument:
    url: str
    title: str | None
    description: str | None
    text: str


class WebPageFetcher:
    """Fetch and distill one public page within explicit safety limits."""

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        max_text_chars: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds or settings.web_page_timeout_seconds
        self.max_bytes = max_bytes or settings.web_page_max_bytes
        self.max_redirects = (
            settings.web_page_max_redirects
            if max_redirects is None
            else max_redirects
        )
        self.max_text_chars = max_text_chars or settings.web_page_max_text_chars
        self.transport = transport

    def fetch(self, url: str) -> WebPageDocument:
        current_url = url
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=timeout,
                transport=self.transport,
                trust_env=False,
                headers={
                    "User-Agent": "TravelPlannerBot/1.0 (+public travel source import)",
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                },
            ) as client:
                for redirect_count in range(self.max_redirects + 1):
                    _require_public_http_url(current_url)
                    with client.stream("GET", current_url) as response:
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location:
                                raise _unavailable("redirect_without_location")
                            if redirect_count >= self.max_redirects:
                                raise _unavailable("too_many_redirects")
                            current_url = urljoin(current_url, location)
                            continue

                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "")
                        media_type = content_type.split(";", 1)[0].strip().lower()
                        if media_type not in _ALLOWED_CONTENT_TYPES:
                            raise AppError(
                                422,
                                "WEB_PAGE_UNSUPPORTED_CONTENT",
                                (
                                    "URL này không trả về một trang văn bản "
                                    "công khai được hỗ trợ."
                                ),
                            )
                        declared_length = _content_length(response)
                        if declared_length is not None and declared_length > self.max_bytes:
                            raise _too_large()
                        body = _read_limited(response, self.max_bytes)
                        encoding = response.encoding or "utf-8"
                        html = body.decode(encoding, errors="replace")
                        break
                else:  # pragma: no cover - loop always exits or raises
                    raise _unavailable("redirect_exhausted")
        except AppError:
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            raise _unavailable(type(exc).__name__) from exc

        metadata = _MetadataParser()
        metadata.feed(html)
        extracted = (
            html
            if media_type == "text/plain"
            else trafilatura.extract(
                html,
                url=current_url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_comments=False,
                favor_precision=True,
            )
        )
        text = (extracted or "").strip()
        if not text:
            raise AppError(
                422,
                "WEB_PAGE_TEXT_NOT_FOUND",
                "Không tìm thấy nội dung văn bản chính trong website này.",
            )
        return WebPageDocument(
            url=canonicalize_url(current_url),
            title=metadata.title,
            description=metadata.description,
            text=text[: self.max_text_chars],
        )


class WebPageExtractionService:
    def __init__(
        self,
        *,
        fetcher: WebPageFetcher | None = None,
        text_structurer: CaptionStructurer | None = None,
        context_extractor: UrlReelContextExtractor | None = None,
    ) -> None:
        self.fetcher = fetcher or WebPageFetcher()
        self.text_structurer = text_structurer
        self.context_extractor = context_extractor or UrlReelContextExtractor()

    def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
        started_at = time.perf_counter()
        fetch_started_at = time.perf_counter()
        document = self.fetcher.fetch(payload.url)
        fetch_seconds = time.perf_counter() - fetch_started_at
        metadata = UrlMetadata(
            originalUrl=payload.url,
            canonicalUrl=document.url,
            platform="web_page",
            title=document.title,
            description=document.description,
        )

        structure_started_at = time.perf_counter()
        structure_result = (
            self.text_structurer.structure(
                caption=document.text,
                metadata=metadata,
                destination=payload.destination,
            )
            if self.text_structurer is not None
            else None
        )
        observations = (
            structure_result.observations
            if structure_result is not None and structure_result.status == "ok"
            else []
        )
        expected_place_count = (
            structure_result.expected_place_count
            if structure_result is not None
            else None
        )
        structuring_seconds = time.perf_counter() - structure_started_at

        context_started_at = time.perf_counter()
        context = self.context_extractor.extract(
            metadata=metadata,
            transcript=document.text,
            speech_observations=observations,
            destination=payload.destination,
            expected_place_count=expected_place_count,
        )
        context = context.model_copy(
            update={
                "extracted_place_details": [
                    place.model_copy(update={"source": "web_page"})
                    for place in context.extracted_place_details
                ]
            }
        )
        context_seconds = time.perf_counter() - context_started_at

        return UrlReelExtractionResult(
            url=payload.url,
            platform="web_page",
            metadata=metadata,
            artifacts=MediaArtifacts(),
            needsImageUpload=False,
            speechToText=SpeechToTextResult(
                text=document.text,
                observations=observations,
                status="ok",
                source="web_page_text",
                durationSeconds=0.0,
            ),
            frameVision=FrameVisionResult(),
            extractedContext=context,
            timings={
                "webPageFetch": fetch_seconds,
                "captionStructuring": structuring_seconds,
                "contextExtraction": context_seconds,
                "totalExtraction": time.perf_counter() - started_at,
            },
        )


def _require_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AppError(
            422,
            "UNSAFE_URL",
            (
                "Website phải dùng HTTP/HTTPS công khai và không chứa "
                "thông tin đăng nhập."
            ),
        )
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise _unsafe_host()
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise _unavailable("dns_resolution_failed") from exc
    if not addresses:
        raise _unavailable("dns_resolution_empty")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:  # pragma: no cover - getaddrinfo returns IPs
            raise _unsafe_host() from exc
        if not address.is_global:
            raise _unsafe_host()


def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("content-length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _unsafe_host() -> AppError:
    return AppError(422, "UNSAFE_URL", "Không thể nhập URL mạng nội bộ.")


def _too_large() -> AppError:
    return AppError(
        422,
        "WEB_PAGE_TOO_LARGE",
        "Website vượt quá kích thước nội dung cho phép.",
    )


def _unavailable(reason: str) -> AppError:
    return AppError(
        502,
        "WEB_PAGE_UNAVAILABLE",
        (
            "Không thể đọc website công khai này. Hãy thử lại hoặc thêm "
            "địa điểm thủ công."
        ),
        details={"reason": reason},
    )


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "title":
            self._in_title = True
            return
        if tag.casefold() != "meta":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        name = (values.get("name") or values.get("property") or "").casefold()
        if name in {"description", "og:description"} and values.get("content"):
            self.description = self.description or values["content"].strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
            value = " ".join(self._title_parts).strip()
            self.title = value or None

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())
