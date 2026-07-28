from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit


class QuietYtdlpLogger:
    def debug(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None


def artifact_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def detect_platform(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return "unknown"
