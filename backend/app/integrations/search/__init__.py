"""Web-search contracts with lazy provider loading.

Importing the base contract must not initialize every optional provider. This
keeps domain code and tests independent from Selenium unless the Google adapter
is actually selected.
"""

from typing import TYPE_CHECKING, Any

from .base import WebSearchProvider, WebSearchResult

if TYPE_CHECKING:
    from .google_selenium import GoogleSeleniumSearchProvider
    from .tavily import TavilySearchProvider

__all__ = [
    "GoogleSeleniumSearchProvider",
    "TavilySearchProvider",
    "WebSearchProvider",
    "WebSearchResult",
]


def __getattr__(name: str) -> Any:
    if name == "GoogleSeleniumSearchProvider":
        from .google_selenium import GoogleSeleniumSearchProvider

        return GoogleSeleniumSearchProvider
    if name == "TavilySearchProvider":
        from .tavily import TavilySearchProvider

        return TavilySearchProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
