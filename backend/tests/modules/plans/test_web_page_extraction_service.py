from __future__ import annotations

import socket

import httpx
import pytest

from app.modules.plans.explorer.tools.url_reels.caption_structurer import (
    CaptionStructureResult,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    MediaArtifacts,
    SpeechToTextObservation,
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import (
    UrlReelExtractionService,
)
from app.modules.plans.explorer.tools.url_reels.utils import canonicalize_url
from app.modules.plans.explorer.tools.web_page.service import (
    WebPageDocument,
    WebPageExtractionService,
    WebPageFetcher,
)
from app.shared.errors import AppError


def _public_dns(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_fetcher_extracts_main_text_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
                <html><head>
                  <title>Ba quán cà phê Hà Nội</title>
                  <meta name="description" content="Một ngày khám phá Hà Nội">
                </head><body>
                  <nav>Đăng nhập | Trang chủ | Quảng cáo</nav>
                  <main><article>
                    <h1>Ba quán cà phê Hà Nội</h1>
                    <p>Buổi sáng ghé Cafe Giảng tại 39 Nguyễn Hữu Huân.</p>
                    <p>Buổi chiều đến Loading T Cafe ở phố Chân Cầm.</p>
                    <p>Buổi tối ngắm hồ từ Highlands Coffee Hàm Cá Mập.</p>
                  </article></main>
                </body></html>
            """,
            request=request,
        )

    document = WebPageFetcher(
        transport=httpx.MockTransport(handler),
    ).fetch("https://example.com/hanoi-cafes")

    assert document.title == "Ba quán cà phê Hà Nội"
    assert document.description == "Một ngày khám phá Hà Nội"
    assert "Cafe Giảng" in document.text
    assert "Loading T Cafe" in document.text


def test_canonical_url_preserves_functional_query_and_drops_tracking() -> None:
    assert canonicalize_url(
        "https://example.com/article?id=42&utm_source=feed&lang=vi#comments"
    ) == "https://example.com/article?id=42&lang=vi"


def test_fetcher_revalidates_and_blocks_private_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolve(host: str, *_args, **_kwargs):
        address = "93.184.216.34" if host == "example.com" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://internal.example/private"},
            request=request,
        )

    with pytest.raises(AppError) as caught:
        WebPageFetcher(transport=httpx.MockTransport(handler)).fetch(
            "https://example.com/article"
        )

    assert caught.value.code == "UNSAFE_URL"


def test_fetcher_rejects_oversized_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 129,
            request=request,
        )

    with pytest.raises(AppError) as caught:
        WebPageFetcher(
            max_bytes=128,
            transport=httpx.MockTransport(handler),
        ).fetch("https://example.com/large")

    assert caught.value.code == "WEB_PAGE_TOO_LARGE"


class _FakeFetcher:
    def fetch(self, url: str) -> WebPageDocument:
        return WebPageDocument(
            url=url,
            title="Một ngày Hà Nội",
            description="Lịch trình cà phê",
            text="Buổi sáng ghé Cafe Giảng tại 39 Nguyễn Hữu Huân.",
        )


class _FakeStructurer:
    def structure(self, *, caption, metadata, destination):
        return CaptionStructureResult(
            observations=[
                SpeechToTextObservation(
                    order=1,
                    placeName="Cafe Giảng",
                    evidence="ghé Cafe Giảng tại 39 Nguyễn Hữu Huân",
                    searchRegion="Hà Nội",
                    addressHint="39 Nguyễn Hữu Huân",
                    timeHint="morning",
                    activity="uống cà phê trứng",
                    confidence=0.95,
                    evidenceSource="caption",
                )
            ],
            expectedPlaceCount=1,
            status="ok",
        )


def test_web_page_extraction_returns_existing_url_contract() -> None:
    result = WebPageExtractionService(
        fetcher=_FakeFetcher(),  # type: ignore[arg-type]
        text_structurer=_FakeStructurer(),  # type: ignore[arg-type]
    ).extract(
        UrlReelInput(
            url="https://example.com/hanoi",
            destination="Hà Nội",
        )
    )

    assert result.platform == "web_page"
    assert result.speech_to_text.source == "web_page_text"
    assert result.extracted_context.extracted_places == ["Cafe Giảng"]
    detail = result.extracted_context.extracted_place_details[0]
    assert detail.source == "web_page"
    assert detail.address == "39 Nguyễn Hữu Huân"


def test_url_service_dispatches_unknown_platform_to_web_page() -> None:
    expected = UrlReelExtractionResult(
        url="https://example.com/article",
        platform="web_page",
        metadata={
            "originalUrl": "https://example.com/article",
            "canonicalUrl": "https://example.com/article",
            "platform": "web_page",
        },
        artifacts=MediaArtifacts(),
        speechToText={"text": "", "status": "ok", "durationSeconds": 0},
        extractedContext=ExtractedContext(),
        timings={"totalExtraction": 0},
    )

    class StubWebPage:
        def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
            return expected

    service = UrlReelExtractionService(
        caption_structurer=_FakeStructurer(),  # type: ignore[arg-type]
        web_page=StubWebPage(),  # type: ignore[arg-type]
    )

    assert service.extract(UrlReelInput(url=expected.url)) is expected
