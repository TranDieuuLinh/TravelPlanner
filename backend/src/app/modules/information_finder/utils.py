import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def content_hash(content: str) -> str:
    normalized = " ".join(content.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Source URL must use HTTP(S) and include a host")
    host = parts.hostname.casefold()
    port = parts.port
    netloc = host if port is None else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parts.scheme.casefold(), netloc, path, query, ""))


def chunk_content(
    content: str,
    *,
    title: str = "",
    destination: str = "",
    target_tokens: int = 300,
    overlap_tokens: int = 50,
) -> list[tuple[str, int]]:
    words = content.split()
    if not words:
        return []
    context = " — ".join(part for part in (title.strip(), destination.strip()) if part)
    prefix = f"{context}\n" if context else ""
    step = max(1, target_tokens - overlap_tokens)
    chunks: list[tuple[str, int]] = []
    for start in range(0, len(words), step):
        body = " ".join(words[start : start + target_tokens])
        if not body:
            break
        chunks.append((prefix + body, len(body.split())))
        if start + target_tokens >= len(words):
            break
    return chunks

