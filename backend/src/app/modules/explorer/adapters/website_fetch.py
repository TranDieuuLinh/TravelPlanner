import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from app.modules.explorer.errors import ExplorerOperationError


class CurlCffiWebsiteFetcher:
    """Safari-impersonated HTTP fallback with bounded redirects and SSRF checks."""

    def __init__(
        self, *, timeout_seconds: float = 30, max_bytes: int = 5_000_000
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def fetch(self, url: str) -> tuple[str, str]:
        return await asyncio.to_thread(self._fetch_sync, url)

    def _fetch_sync(self, url: str) -> tuple[str, str]:
        from curl_cffi import requests

        current = url
        for _ in range(4):
            self._validate_public_url(current)
            try:
                response = requests.get(
                    current,
                    impersonate="safari",
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                    headers={"accept-language": "vi-VN,vi;q=0.9,en;q=0.8"},
                )
            except Exception as exc:
                raise ExplorerOperationError(
                    "WEB_IMPERSONATED_DOWNLOAD_FAILED",
                    "curl-cffi không tải được website.",
                    retryable=True,
                ) from exc
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location:
                    break
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise ExplorerOperationError(
                    "WEB_IMPERSONATED_DOWNLOAD_FAILED",
                    f"Website trả HTTP {response.status_code} qua curl-cffi.",
                    retryable=response.status_code >= 500,
                )
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                raise ExplorerOperationError(
                    "WEB_CONTENT_UNSUPPORTED", "URL không trả nội dung HTML."
                )
            if len(response.content) > self.max_bytes:
                raise ExplorerOperationError(
                    "WEB_CONTENT_TOO_LARGE", "Website vượt giới hạn tải."
                )
            return response.text, str(response.url)
        raise ExplorerOperationError(
            "WEB_REDIRECT_LIMIT", "Website redirect quá nhiều lần qua curl-cffi."
        )

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            raise ExplorerOperationError("UNSUPPORTED_URL", "Website URL không hợp lệ.")
        try:
            records = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ExplorerOperationError(
                "WEB_DNS_FAILED", "Không phân giải được website.", retryable=True
            ) from exc
        if any(
            not ipaddress.ip_address(record[4][0]).is_global for record in records
        ):
            raise ExplorerOperationError(
                "WEB_PRIVATE_ADDRESS", "Website trỏ đến địa chỉ nội bộ bị chặn."
            )
