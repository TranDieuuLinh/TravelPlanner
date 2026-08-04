from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel


_REDACTED_KEYS = {
    "password",
    "passwordHash",
    "password_hash",
    "accessToken",
    "refreshToken",
    "csrfToken",
    "token",
    "secret",
    "apiKey",
    "api_key",
    "raw",
    "rawPayload",
    "raw_payload",
    "systemPrompt",
    "system_prompt",
    "previousOutput",
}
_COUNT_ONLY_KEYS = {
    "imageContexts",
    "image_contexts",
    "framePaths",
    "frame_paths",
}
_TEXT_SUMMARY_KEYS = {
    "rawRequest",
    "raw_request",
    "transcript",
}
_MAX_STRING_LENGTH = 2_000


def safe_snapshot(value: Any) -> Any:
    """Convert structured planning data to bounded, redacted JSON."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in _REDACTED_KEYS:
                result[key] = "[redacted]"
            elif key in _COUNT_ONLY_KEYS:
                result[key] = {"count": len(item) if isinstance(item, Sequence) else 0}
            elif key in _TEXT_SUMMARY_KEYS:
                text = str(item or "")
                result[key] = {
                    "characterCount": len(text),
                    "present": bool(text.strip()),
                }
            else:
                result[key] = safe_snapshot(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [safe_snapshot(item) for item in value[:500]]
    if isinstance(value, (bytes, bytearray)):
        return {"byteCount": len(value)}
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            value = _strip_url_secrets(value)
        if len(value) > _MAX_STRING_LENGTH:
            return value[:_MAX_STRING_LENGTH] + "…"
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _strip_url_secrets(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
