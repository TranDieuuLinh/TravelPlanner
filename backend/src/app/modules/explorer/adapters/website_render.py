import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.modules.explorer.errors import ExplorerOperationError


class PlaywrightWebsiteRenderer:
    """Bounded browser fallback for public pages that reject plain HTTP."""

    def __init__(self, *, timeout_seconds: float = 30) -> None:
        self.timeout_ms = round(timeout_seconds * 1000)
        self._host_access: dict[str, bool] = {}

    async def render(self, url: str) -> tuple[str, str]:
        await self._require_public(url)
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ExplorerOperationError(
                "WEB_BROWSER_UNAVAILABLE",
                "Playwright chưa được cài cho website fallback.",
            ) from exc

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        locale="vi-VN",
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                    )
                    page = await context.new_page()
                    await page.route("**/*", self._route_request)
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )
                    await self._require_public(page.url)
                    if response is not None and response.status >= 400:
                        raise ExplorerOperationError(
                            "WEB_BROWSER_DOWNLOAD_FAILED",
                            f"Website trả HTTP {response.status} trong Playwright.",
                        )
                    await page.wait_for_timeout(1000)
                    return await page.content(), page.url
                finally:
                    await browser.close()
        except ExplorerOperationError:
            raise
        except Exception as exc:
            raise ExplorerOperationError(
                "WEB_BROWSER_DOWNLOAD_FAILED",
                "Playwright không tải được website.",
                retryable=True,
            ) from exc

    async def _route_request(self, route) -> None:
        request = route.request
        if request.resource_type in {"image", "media", "font"}:
            await route.abort()
            return
        parsed = urlparse(request.url)
        if parsed.scheme in {"data", "blob"}:
            await route.continue_()
            return
        try:
            await self._require_public(request.url)
        except ExplorerOperationError:
            await route.abort()
            return
        await route.continue_()

    async def _require_public(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            raise ExplorerOperationError("UNSUPPORTED_URL", "Website URL không hợp lệ.")
        cached = self._host_access.get(host)
        if cached is False:
            raise ExplorerOperationError(
                "WEB_PRIVATE_ADDRESS", "Website trỏ đến địa chỉ nội bộ bị chặn."
            )
        if cached is True:
            return
        try:
            records = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except socket.gaierror as exc:
            raise ExplorerOperationError(
                "WEB_DNS_FAILED", "Không phân giải được website.", retryable=True
            ) from exc
        allowed = all(
            ipaddress.ip_address(record[4][0]).is_global for record in records
        )
        self._host_access[host] = allowed
        if not allowed:
            raise ExplorerOperationError(
                "WEB_PRIVATE_ADDRESS", "Website trỏ đến địa chỉ nội bộ bị chặn."
            )
