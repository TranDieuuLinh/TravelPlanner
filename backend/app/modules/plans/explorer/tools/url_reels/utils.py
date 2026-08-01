from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


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
    host = parts.netloc.lower().split(":", 1)[0].removeprefix("www.")
    query = ""
    if host in {
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        video_ids = parse_qs(parts.query).get("v", [])
        if video_ids:
            query = urlencode({"v": video_ids[0]})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


_YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def extract_youtube_video_id(url: str) -> str | None:
    parts = urlsplit(url)
    host = parts.netloc.lower().split(":", 1)[0].removeprefix("www.")
    candidate: str | None = None
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parts.path.rstrip("/") == "/watch":
            candidate = next(iter(parse_qs(parts.query).get("v", [])), None)
        else:
            path_parts = parts.path.strip("/").split("/")
            if len(path_parts) >= 2 and path_parts[0] in {
                "embed",
                "live",
                "shorts",
            }:
                candidate = path_parts[1]
    if candidate and _YOUTUBE_VIDEO_ID.fullmatch(candidate):
        return candidate
    return None


def detect_platform(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return "unknown"
