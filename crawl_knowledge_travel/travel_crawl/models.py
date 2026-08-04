from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "travel-source-record.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(source: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source}\0{external_id}".encode("utf-8")).hexdigest()[:24]
    return f"{source}:{digest}"


@dataclass(slots=True)
class SourceRecord:
    record_id: str
    source: str
    source_url: str
    record_type: str
    title: str
    license: str
    retrieved_at: str
    language: str | None = None
    text: str | None = None
    destination_hints: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    content_sha256: str = ""
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        source: str,
        external_id: str,
        source_url: str,
        record_type: str,
        title: str,
        license: str,
        retrieved_at: str | None = None,
        language: str | None = None,
        text: str | None = None,
        destination_hints: list[str] | None = None,
        sections: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "SourceRecord":
        body = {
            "title": title,
            "text": text,
            "sections": sections or {},
            "payload": payload or {},
        }
        content_sha = hashlib.sha256(
            json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return cls(
            record_id=stable_id(source, external_id),
            source=source,
            source_url=source_url,
            record_type=record_type,
            title=title.strip(),
            license=license,
            retrieved_at=retrieved_at or utc_now(),
            language=language,
            text=text.strip() if text else None,
            destination_hints=list(dict.fromkeys(destination_hints or [])),
            sections=sections or {},
            payload=payload or {},
            content_sha256=content_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceRecord":
        return cls(**value)
