from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import json
import re
from typing import Any

from pydantic import BaseModel

_SENSITIVE_KEY_SUBSTRINGS = (
    "key",
    "secret",
    "password",
    "token",
    "auth",
    "cookie",
    "credential",
    "database_url",
    "private",
)

_SENSITIVE_REGEXES = (
    # Google API Key: AIzaSy...
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    # Langfuse API Keys: pk-lf-..., sk-lf-...
    re.compile(r"(?:pk|sk)-lf-[a-f0-9\-]{20,}"),
    # Bearer tokens
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
    # Database connection strings with passwords: postgres://user:pass@host...
    re.compile(r"(postgres(?:ql)?:\/\/[^:]+:)([^@]+)(@)", re.IGNORECASE),
)

_REDACTED_TEXT = "[REDACTED]"


def redact_string(text: str, max_chars: int | None = None) -> str:
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in _SENSITIVE_REGEXES:
        if pattern.groups == 3:
            redacted = pattern.sub(r"\1" + _REDACTED_TEXT + r"\3", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\1" + _REDACTED_TEXT, redacted)
        else:
            redacted = pattern.sub(_REDACTED_TEXT, redacted)
    if max_chars is not None and max_chars > 0 and len(redacted) > max_chars:
        truncated_count = len(redacted) - max_chars
        redacted = redacted[:max_chars] + f"... [truncated {truncated_count} chars]"
    return redacted


def is_sensitive_key(key: str) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return any(substring in normalized for substring in _SENSITIVE_KEY_SUBSTRINGS)


def sanitize_payload(
    obj: Any,
    max_depth: int = 4,
    max_chars: int = 2000,
    max_items: int = 50,
    _seen: set[int] | None = None,
) -> Any:
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return redact_string(obj, max_chars=max_chars)

    if _seen is None:
        _seen = set()
    obj_id = id(obj)
    if obj_id in _seen:
        return "[CIRCULAR]"
    if max_depth <= 0:
        return "[DEPTH_EXCEEDED]"

    _seen.add(obj_id)
    try:
        if isinstance(obj, BaseModel):
            data = obj.model_dump(mode="json", exclude_none=True)
            return sanitize_payload(data, max_depth - 1, max_chars, max_items, _seen)
        if is_dataclass(obj) and not isinstance(obj, type):
            # ``dataclasses.asdict`` deep-copies values and therefore fails for
            # immutable runtime state such as ``types.MappingProxyType``.
            data = {field.name: getattr(obj, field.name) for field in fields(obj)}
            return sanitize_payload(data, max_depth - 1, max_chars, max_items, _seen)
        if isinstance(obj, Mapping):
            sanitized_dict: dict[str, Any] = {}
            for index, (key, value) in enumerate(obj.items()):
                if index >= max_items:
                    sanitized_dict["_omitted_keys"] = f"{len(obj) - max_items} more items"
                    break
                str_key = str(key)
                if is_sensitive_key(str_key):
                    sanitized_dict[str_key] = _REDACTED_TEXT
                else:
                    sanitized_dict[str_key] = sanitize_payload(
                        value, max_depth - 1, max_chars, max_items, _seen
                    )
            return sanitized_dict
        if isinstance(obj, (list, tuple, set)):
            sanitized_list = []
            for index, item in enumerate(obj):
                if index >= max_items:
                    sanitized_list.append(f"... and {len(obj) - max_items} more items")
                    break
                sanitized_list.append(
                    sanitize_payload(item, max_depth - 1, max_chars, max_items, _seen)
                )
            return sanitized_list
        return redact_string(str(obj), max_chars=max_chars)
    finally:
        _seen.remove(obj_id)


def safe_preview(obj: Any, max_chars: int = 2000) -> str | None:
    if obj is None:
        return None
    sanitized = sanitize_payload(obj, max_chars=max_chars)
    if isinstance(sanitized, str):
        return sanitized
    try:
        return json.dumps(sanitized, ensure_ascii=False)
    except (TypeError, ValueError):
        return redact_string(str(sanitized), max_chars=max_chars)
