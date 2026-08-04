from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    content: bytes
    headers: dict[str, str]

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        match = "utf-8"
        if "charset=" in content_type:
            match = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        try:
            return self.content.decode(match, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


class PoliteHttpClient:
    def __init__(
        self,
        *,
        delay_seconds: float = 2.5,
        timeout_seconds: float = 30,
        max_retries: int = 3,
        user_agent: str = "VSF-Travel-Knowledge-Collector/1.0 (+local research; contact=developer)",
    ) -> None:
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._last_request_at: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "vi,en;q=0.8"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _wait_for_host(self, url: str) -> None:
        host = urlparse(url).netloc.casefold()
        elapsed = time.monotonic() - self._last_request_at.get(host, 0.0)
        # A small jitter avoids repeatedly hitting a host on an exact cadence.
        remaining = self.delay_seconds + random.uniform(0.0, 0.5) - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()

    def _request(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchResult:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait_for_host(url)
            try:
                response = self._client.get(url, params=params)
                if response.status_code in {429, 500, 502, 503, 504}:
                    delay = min(30.0, self._retry_delay(response, attempt))
                    logger.warning("Retryable HTTP %s for %s; waiting %.1fs", response.status_code, url, delay)
                    time.sleep(delay)
                    continue
                if response.status_code not in (allowed_statuses or set()):
                    response.raise_for_status()
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    content=response.content,
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if 400 <= status_code < 500 and status_code != 429:
                    raise RuntimeError(f"Non-retryable HTTP {status_code} for {url}") from exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(30.0, (2**attempt) + random.random()))
            except (httpx.RequestError, OSError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(30.0, (2**attempt) + random.random()))
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("retry-after")
        if value:
            try:
                return float(value)
            except ValueError:
                try:
                    return max(0.0, (parsedate_to_datetime(value).timestamp() - time.time()))
                except (TypeError, ValueError):
                    pass
        return (2**attempt) + random.random()

    def _robot_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = urljoin(origin, "/robots.txt")
        try:
            result = self._request(robots_url, allowed_statuses={404, 410})
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(result.text.splitlines() if result.status_code == 200 else [])
            self._robots[origin] = parser
        except RuntimeError:
            logger.warning("Could not read robots.txt for %s; skipping site pages", origin)
            self._robots[origin] = None
        return self._robots[origin]

    def get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        respect_robots: bool = True,
    ) -> FetchResult:
        if respect_robots:
            parser = self._robot_parser(url)
            if parser is None or not parser.can_fetch(self.user_agent, url):
                raise PermissionError(f"robots.txt does not allow collection: {url}")
        return self._request(url, params=params)
