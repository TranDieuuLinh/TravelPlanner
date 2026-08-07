from __future__ import annotations

import asyncio
import ipaddress
import time
from collections.abc import Callable
from urllib.parse import quote_plus, urlsplit

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from .base import WebSearchResult


class GoogleSeleniumSearchProvider:
    """Open Google's first organic result and return its rendered page text."""

    provider_name = "google_selenium"

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        min_interval_seconds: float = 8.0,
        page_load_wait_seconds: float = 3.0,
        post_search_delay_seconds: float = 1.0,
        max_content_chars: int = 20_000,
        headless: bool = True,
        driver_factory: Callable[[], WebDriver] | None = None,
    ) -> None:
        self.timeout_seconds = max(5.0, timeout_seconds)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.page_load_wait_seconds = max(0.0, page_load_wait_seconds)
        self.post_search_delay_seconds = max(0.0, post_search_delay_seconds)
        self.max_content_chars = max(1_000, max_content_chars)
        self.headless = headless
        self.driver_factory = driver_factory
        self._interval_lock = asyncio.Lock()
        self._last_search_started_at = 0.0

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        del limit
        cleaned = query.strip()
        if not cleaned:
            return []
        await self._wait_for_interval()
        try:
            return await asyncio.to_thread(self._search_sync, cleaned)
        finally:
            if self.post_search_delay_seconds > 0:
                await asyncio.sleep(self.post_search_delay_seconds)

    async def _wait_for_interval(self) -> None:
        async with self._interval_lock:
            remaining = (
                self._last_search_started_at + self.min_interval_seconds
                - time.monotonic()
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_search_started_at = time.monotonic()

    def _search_sync(self, query: str) -> list[WebSearchResult]:
        driver: WebDriver | None = None
        try:
            driver = self._create_driver()
            driver.set_page_load_timeout(self.timeout_seconds)
            search_url = (
                "https://www.google.com/search?hl=vi&q="
                f"{quote_plus(query)}"
            )
            driver.get(search_url)
            self._raise_if_google_blocked(driver)
            link = self._first_result_link(driver)
            if link is None:
                return []

            result_title = str(link.get_attribute("aria-label") or "").strip()
            if not result_title:
                headings = link.find_elements(By.TAG_NAME, "h3")
                result_title = headings[0].text.strip() if headings else ""

            original_handles = set(driver.window_handles)
            link.click()
            WebDriverWait(driver, self.timeout_seconds).until(
                lambda current: (
                    current.current_url != search_url
                    or set(current.window_handles) != original_handles
                )
            )
            new_handles = [
                handle
                for handle in driver.window_handles
                if handle not in original_handles
            ]
            if new_handles:
                driver.switch_to.window(new_handles[-1])
            WebDriverWait(driver, self.timeout_seconds).until(
                lambda current: current.execute_script(
                    "return document.readyState"
                )
                in {"interactive", "complete"}
            )
            if self.page_load_wait_seconds > 0:
                time.sleep(self.page_load_wait_seconds)

            final_url = driver.current_url.strip()
            if not _is_safe_public_url(final_url):
                raise RuntimeError("google_selenium_unsafe_result")
            body = driver.find_element(By.TAG_NAME, "body").text
            content = _normalize_page_text(body, self.max_content_chars)
            if not content:
                return []
            title = driver.title.strip() or result_title or final_url
            return [
                WebSearchResult(
                    title=title[:500],
                    uri=final_url[:2048],
                    snippet=content,
                )
            ]
        except TimeoutException as exc:
            raise RuntimeError("google_selenium_timeout") from exc
        except WebDriverException as exc:
            raise RuntimeError("google_selenium_error") from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException:
                    pass

    def _create_driver(self) -> WebDriver:
        if self.driver_factory is not None:
            return self.driver_factory()
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--lang=vi-VN")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_experimental_option(
            "prefs",
            {"profile.managed_default_content_settings.images": 2},
        )
        options.page_load_strategy = "eager"
        return webdriver.Chrome(options=options)

    @staticmethod
    def _first_result_link(driver: WebDriver):
        for link in driver.find_elements(By.CSS_SELECTOR, "#search a"):
            href = str(link.get_attribute("href") or "").strip()
            if not _is_safe_public_url(href) or _is_google_url(href):
                continue
            if not link.find_elements(By.TAG_NAME, "h3"):
                continue
            return link
        return None

    @staticmethod
    def _raise_if_google_blocked(driver: WebDriver) -> None:
        current_url = driver.current_url.casefold()
        body = driver.find_element(By.TAG_NAME, "body").text.casefold()
        blocked_markers = (
            "unusual traffic",
            "our systems have detected",
            "captcha",
            "lưu lượng truy cập bất thường",
        )
        if (
            "consent.google." in current_url
            or "/sorry/" in current_url
            or any(marker in body for marker in blocked_markers)
        ):
            raise RuntimeError("google_selenium_blocked")


def _is_google_url(uri: str) -> bool:
    try:
        hostname = (urlsplit(uri).hostname or "").casefold()
    except ValueError:
        return False
    return hostname == "google.com" or hostname.endswith(".google.com")


def _is_safe_public_url(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        hostname_value = parsed.hostname
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not hostname_value:
        return False
    hostname = hostname_value.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _normalize_page_text(value: str, max_chars: int) -> str:
    lines = (" ".join(line.split()) for line in value.splitlines())
    cleaned = "\n".join(line for line in lines if line)
    return cleaned[:max_chars]
