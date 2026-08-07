from __future__ import annotations

import asyncio

from selenium.webdriver.common.by import By

from app.integrations.search.google_selenium import (
    GoogleSeleniumSearchProvider,
    _is_safe_public_url,
    _normalize_page_text,
)


class FakeElement:
    def __init__(
        self,
        *,
        text: str = "",
        href: str = "",
        heading: str = "",
        on_click=None,
    ) -> None:
        self.text = text
        self.href = href
        self.heading = heading
        self.on_click = on_click

    def get_attribute(self, name: str):
        if name == "href":
            return self.href
        if name == "aria-label":
            return ""
        return None

    def find_elements(self, by: str, value: str):
        if by == By.TAG_NAME and value == "h3" and self.heading:
            return [FakeElement(text=self.heading)]
        return []

    def click(self) -> None:
        if self.on_click is not None:
            self.on_click()


class FakeSwitchTo:
    def window(self, handle: str) -> None:
        del handle


class FakeDriver:
    def __init__(self) -> None:
        self.current_url = ""
        self.window_handles = ["main"]
        self.switch_to = FakeSwitchTo()
        self.title = "Vé tham quan chính thức"
        self.quit_called = False
        self.search_query_url = ""

    def set_page_load_timeout(self, timeout: float) -> None:
        assert timeout == 10

    def get(self, url: str) -> None:
        self.current_url = url
        self.search_query_url = url

    def find_element(self, by: str, value: str):
        assert by == By.TAG_NAME and value == "body"
        if "google.com/search" in self.current_url:
            return FakeElement(text="Kết quả tìm kiếm")
        return FakeElement(text="Giá vé người lớn\n  70.000 VND ")

    def find_elements(self, by: str, value: str):
        assert by == By.CSS_SELECTOR and value == "#search a"
        return [
            FakeElement(
                href="https://www.google.com/preferences",
                heading="Google preference",
            ),
            FakeElement(
                href="https://official.example/tickets",
                heading="Official tickets",
                on_click=self._open_result,
            ),
        ]

    def execute_script(self, script: str):
        assert script == "return document.readyState"
        return "complete"

    def quit(self) -> None:
        self.quit_called = True

    def _open_result(self) -> None:
        self.current_url = "https://official.example/tickets"


def test_google_selenium_opens_first_result_and_returns_page_content() -> None:
    driver = FakeDriver()
    provider = GoogleSeleniumSearchProvider(
        timeout_seconds=10,
        min_interval_seconds=0,
        page_load_wait_seconds=0,
        post_search_delay_seconds=0,
        driver_factory=lambda: driver,
    )

    results = asyncio.run(
        provider.search("giá vé của Văn Miếu", limit=8)
    )

    assert "q=gi%C3%A1+v%C3%A9+c%E1%BB%A7a+V%C4%83n+Mi%E1%BA%BFu" in (
        driver.search_query_url
    )
    assert results[0].uri == "https://official.example/tickets"
    assert results[0].snippet == "Giá vé người lớn\n70.000 VND"
    assert driver.quit_called is True


def test_google_selenium_rejects_local_and_non_http_urls() -> None:
    assert _is_safe_public_url("https://example.test/tickets") is True
    assert _is_safe_public_url("http://127.0.0.1/private") is False
    assert _is_safe_public_url("http://localhost/private") is False
    assert _is_safe_public_url("javascript:alert(1)") is False


def test_google_selenium_normalizes_and_bounds_page_text() -> None:
    assert _normalize_page_text("  Giá   vé \n\n 70.000 VND ", 12) == (
        "Giá vé\n70.00"
    )
