import asyncio

from app.modules.explorer.adapters import url_sources
from app.modules.explorer.adapters.url_sources import WebsiteSourceExtractor
from app.modules.explorer.errors import ExplorerOperationError


def test_website_uses_trafilatura_markdown() -> None:
    class FakeFetcher:
        async def fetch(self, url: str):
            return (
                "<html><body><article><h1>Hà Nội</h1>"
                "<p>Văn Miếu có nhiều thông tin hữu ích cho du khách.</p>"
                "</article></body></html>",
                url,
            )

    result = asyncio.run(WebsiteSourceExtractor(
        impersonated_fetcher=FakeFetcher()
    ).extract("https://example.com/hanoi", source_index=0, raw_prompt=None))

    assert result.artifacts[0].artifact_type == "web_text"
    assert "Văn Miếu" in result.artifacts[0].text


def test_website_falls_back_to_renderer_after_curl_cffi_block() -> None:
    class BlockedFetcher:
        async def fetch(self, url: str):
            raise ExplorerOperationError(
                "WEB_IMPERSONATED_DOWNLOAD_FAILED", "Website trả HTTP 403."
            )

    class FakeRenderer:
        async def render(self, url: str):
            return (
                "<html><article><h1>Hà Nội</h1>"
                "<p>Chợ Đồng Xuân đóng cửa lúc 18:00.</p></article></html>",
                url,
            )

    result = asyncio.run(WebsiteSourceExtractor(
        impersonated_fetcher=BlockedFetcher(),
        renderer=FakeRenderer(),
    ).extract("https://example.com/hanoi", source_index=0, raw_prompt=None))

    assert result.status == "succeeded"
    assert "Chợ Đồng Xuân" in result.artifacts[0].text


def test_website_prefers_curl_cffi_before_browser() -> None:
    class FakeFetcher:
        async def fetch(self, url: str):
            return (
                "<html><article><h1>Hà Nội</h1>"
                "<p>Phố Cổ có quán cà phê, cửa hàng và chợ đêm.</p>"
                "</article></html>",
                url,
            )

    class BrowserMustNotRun:
        async def render(self, url: str):
            raise AssertionError("Playwright should be the final fallback")

    result = asyncio.run(WebsiteSourceExtractor(
        impersonated_fetcher=FakeFetcher(),
        renderer=BrowserMustNotRun(),
    ).extract("https://example.com/hanoi", source_index=0, raw_prompt=None))

    assert "chợ đêm" in result.artifacts[0].text


def test_website_renders_when_curl_cffi_html_has_no_main_text(monkeypatch) -> None:
    monkeypatch.setattr(
        url_sources.trafilatura,
        "extract",
        lambda html, **_: "Hồ Hoàn Kiếm mở cửa cả ngày." if "Hồ" in html else None,
    )

    class EmptyFetcher:
        async def fetch(self, url: str):
            return "<html><body><nav>Menu</nav></body></html>", url

    class FakeRenderer:
        async def render(self, url: str):
            return (
                "<html><article><p>Hồ Hoàn Kiếm mở cửa cả ngày.</p>"
                "</article></html>",
                url,
            )

    result = asyncio.run(WebsiteSourceExtractor(
        impersonated_fetcher=EmptyFetcher(),
        renderer=FakeRenderer(),
    ).extract("https://example.com/hanoi", source_index=0, raw_prompt=None))

    assert "Hồ Hoàn Kiếm" in result.artifacts[0].text
