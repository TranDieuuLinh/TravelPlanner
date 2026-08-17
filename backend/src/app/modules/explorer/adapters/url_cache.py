import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.modules.explorer.models import (
    SourceArtifact,
    SourceBranchFailure,
    SourceExtractionResult,
)
from app.modules.explorer.adapters.postgres import asyncpg_dsn


EXPLORER_URL_CACHE_VERSION = "8"
_LEGACY_CACHE_VERSIONS = {"6"}
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "igshid"}
_QUERYLESS_SOCIAL_HOST_SUFFIXES = (
    "facebook.com",
    "instagram.com",
    "tiktok.com",
)


def canonicalize_source_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    if any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _QUERYLESS_SOCIAL_HOST_SUFFIXES
    ):
        query_items = []
    else:
        query_items = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_QUERY_KEYS
            and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
        ]
    if host == "youtu.be" and path.strip("/"):
        host = "www.youtube.com"
        netloc = host
        query_items = [("v", path.strip("/")), *query_items]
        path = "/watch"
    query = urlencode(query_items)
    return urlunsplit((scheme, netloc, path, query, ""))


def _platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return "youtube"
    return "web_page"


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _legacy_artifacts(value: dict, canonical_url: str) -> list[SourceArtifact]:
    artifacts = []
    type_map = {
        "caption": "caption",
        "stt": "stt",
        "ocr": "frame_ocr",
        "web_page_text": "web_text",
    }
    for legacy_type, language_items in value.items():
        artifact_type = type_map.get(legacy_type)
        if artifact_type is None or not isinstance(language_items, dict):
            continue
        for language, item in language_items.items():
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            artifacts.append(SourceArtifact(
                artifactType=artifact_type,
                text=text.strip()[:60_000],
                sourceUrl=canonical_url,
                language=None if language == "_" else str(language)[:20],
            ))
    return artifacts


def _decode_artifacts(value, version: str, canonical_url: str) -> list[SourceArtifact]:
    data = _json_value(value)
    if version in _LEGACY_CACHE_VERSIONS and isinstance(data, dict):
        return _legacy_artifacts(data, canonical_url)
    if version == EXPLORER_URL_CACHE_VERSION and isinstance(data, list):
        return [SourceArtifact.model_validate(item) for item in data]
    return []


def _decode_failures(context, version: str) -> list[SourceBranchFailure]:
    if version != EXPLORER_URL_CACHE_VERSION:
        return []
    data = _json_value(context)
    if not isinstance(data, dict):
        return []
    return [
        SourceBranchFailure.model_validate(item)
        for item in data.get("branchFailures", [])
    ]


def _decode_coverage(context, version: str) -> dict:
    if version != EXPLORER_URL_CACHE_VERSION:
        return {}
    data = _json_value(context)
    if not isinstance(data, dict):
        return {}
    return {
        key: data[key]
        for key in (
            "sourceDurationSeconds",
            "analyzedDurationSeconds",
            "coverageRatio",
            "coverageStatus",
        )
        if key in data
    }


class InMemoryUrlSourceCache:
    def __init__(self) -> None:
        self._items: dict[str, SourceExtractionResult] = {}

    async def get(
        self, url: str, *, source_index: int
    ) -> SourceExtractionResult | None:
        item = self._items.get(canonicalize_source_url(url))
        if item is None:
            return None
        return item.model_copy(update={
            "source_index": source_index,
            "source_ref": url,
            "cache_status": "hit",
        }, deep=True)

    async def save(self, url: str, result: SourceExtractionResult) -> None:
        self._items[canonicalize_source_url(url)] = result.model_copy(deep=True)


class PostgresUrlSourceCache:
    """Explorer-owned adapter for the adopted legacy source_documents table."""

    def __init__(
        self,
        database_url: str,
        *,
        ttl_seconds: float = 604_800,
        command_timeout: float = 15,
    ) -> None:
        self.database_url = asyncpg_dsn(database_url)
        self.ttl_seconds = ttl_seconds
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg  # type: ignore[import-untyped]

            self._pool = await asyncpg.create_pool(
                self.database_url,
                command_timeout=self.command_timeout,
                min_size=0,
                max_size=1,
            )
        return self._pool

    async def get(
        self, url: str, *, source_index: int
    ) -> SourceExtractionResult | None:
        canonical_url = canonicalize_source_url(url)
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT platform, artifacts, extracted_context,
                          extractor_version, fetched_at
                   FROM source_documents
                   WHERE canonical_url=$1
                     AND extractor_version = ANY($2::varchar[])
                     AND fetched_at >= now() - ($3 * interval '1 second')""",
                canonical_url,
                [EXPLORER_URL_CACHE_VERSION, *_LEGACY_CACHE_VERSIONS],
                self.ttl_seconds,
            )
        if row is None:
            return None
        version = str(row["extractor_version"] or "")
        artifacts = _decode_artifacts(row["artifacts"], version, canonical_url)
        if not artifacts:
            return None
        failures = _decode_failures(row["extracted_context"], version)
        coverage = _decode_coverage(row["extracted_context"], version)
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="url",
            sourceRef=url,
            status="partial" if failures else "succeeded",
            artifacts=artifacts,
            branchFailures=failures,
            cacheStatus="hit",
            **coverage,
        )

    async def save(self, url: str, result: SourceExtractionResult) -> None:
        if result.status not in {"succeeded", "partial"} or not result.artifacts:
            return
        canonical_url = canonicalize_source_url(url)
        artifacts = [
            artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
            for artifact in result.artifacts
        ]
        context = {
            "_cacheVersion": int(EXPLORER_URL_CACHE_VERSION),
            "status": result.status,
            "sourceDurationSeconds": result.source_duration_seconds,
            "analyzedDurationSeconds": result.analyzed_duration_seconds,
            "coverageRatio": result.coverage_ratio,
            "coverageStatus": result.coverage_status,
            "branchFailures": [
                failure.model_dump(mode="json", by_alias=True, exclude_none=True)
                for failure in result.branch_failures
            ],
        }
        artifact_json = json.dumps(artifacts, ensure_ascii=False, sort_keys=True)
        context_json = json.dumps(context, ensure_ascii=False, sort_keys=True)
        artifact_hash = hashlib.sha256(artifact_json.encode()).hexdigest()
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO source_documents
                   (id, canonical_url, platform, artifacts, extracted_context,
                    artifact_hash, extractor_version, fetched_at, created_at, updated_at)
                   VALUES ($1,$2,$3,$4::json,$5::json,$6,$7,now(),now(),now())
                   ON CONFLICT (canonical_url) DO UPDATE SET
                     platform=EXCLUDED.platform,
                     artifacts=EXCLUDED.artifacts,
                     extracted_context=EXCLUDED.extracted_context,
                     artifact_hash=EXCLUDED.artifact_hash,
                     extractor_version=EXCLUDED.extractor_version,
                     fetched_at=now(), updated_at=now()""",
                str(uuid4()),
                canonical_url,
                _platform(canonical_url),
                artifact_json,
                context_json,
                artifact_hash,
                EXPLORER_URL_CACHE_VERSION,
            )
