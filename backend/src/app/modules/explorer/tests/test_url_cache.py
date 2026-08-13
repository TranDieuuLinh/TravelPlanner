import asyncio

from app.modules.explorer.adapters.url_cache import (
    InMemoryUrlSourceCache,
    _decode_artifacts,
    _decode_coverage,
    canonicalize_source_url,
)
from app.modules.explorer.adapters.postgres import asyncpg_dsn
from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult
from app.modules.explorer.service import ExplorerService


class CountingUrlExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, url, *, source_index, raw_prompt):
        self.calls += 1
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="url",
            sourceRef=url,
            status="succeeded",
            artifacts=[SourceArtifact(
                artifactType="caption",
                text="Huế",
                sourceUrl=url,
                language="vi",
            )],
        )


class UnusedDependency:
    pass


class BrokenCache:
    async def get(self, url, *, source_index):
        raise RuntimeError("cache unavailable")

    async def save(self, url, result):
        raise RuntimeError("cache unavailable")


def service_with(extractor: CountingUrlExtractor, cache=None) -> ExplorerService:
    unused = UnusedDependency()
    return ExplorerService(
        drafts=unused,
        url_extractor=extractor,
        image_extractor=unused,
        snapshots=unused,
        url_cache=cache or InMemoryUrlSourceCache(),
    )


def extract(service: ExplorerService, payload: ExplorerInput):
    return asyncio.run(service.extract_sources(payload))[0]


def test_canonical_url_removes_trackers_and_normalizes_youtube() -> None:
    assert canonicalize_source_url(
        "HTTPS://youtu.be/abc123/?utm_source=x&t=7#caption"
    ) == "https://www.youtube.com/watch?v=abc123&t=7"


def test_canonical_url_removes_all_tiktok_query_parameters() -> None:
    assert canonicalize_source_url(
        "https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510"
        "?q=things%20to%20do%20in%20Hanoi&t=1786464699496"
    ) == "https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510"


def test_asyncpg_dsn_accepts_sqlalchemy_postgres_schemes() -> None:
    assert asyncpg_dsn("postgresql+psycopg://user:pass@db/app") == (
        "postgresql://user:pass@db/app"
    )
    assert asyncpg_dsn("postgresql+asyncpg://user:pass@db/app") == (
        "postgresql://user:pass@db/app"
    )


def test_legacy_v6_artifacts_are_converted_to_current_contract() -> None:
    artifacts = _decode_artifacts(
        {
            "caption": {"vi": {"text": "Đi Huế", "source": "caption"}},
            "ocr": {"_": {"text": "Chợ Đông Ba", "source": "ocr"}},
        },
        "6",
        "https://www.tiktok.com/@a/video/1",
    )

    assert [item.artifact_type for item in artifacts] == ["caption", "frame_ocr"]
    assert artifacts[0].language == "vi"
    assert artifacts[1].language is None


def test_current_cache_context_restores_transcript_coverage() -> None:
    coverage = _decode_coverage(
        {
            "sourceDurationSeconds": 5865,
            "analyzedDurationSeconds": 5865,
            "coverageRatio": 1.0,
            "coverageStatus": "complete",
        },
        "8",
    )

    assert coverage == {
        "sourceDurationSeconds": 5865,
        "analyzedDurationSeconds": 5865,
        "coverageRatio": 1.0,
        "coverageStatus": "complete",
    }


def test_cache_hit_skips_second_url_extraction() -> None:
    extractor = CountingUrlExtractor()
    service = service_with(extractor)

    first = extract(service, ExplorerInput(urls=["https://example.com/post?utm_source=x"]))
    second = extract(service, ExplorerInput(urls=["https://example.com/post"]))

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert extractor.calls == 1


def test_force_refresh_bypasses_hit_and_replaces_cache() -> None:
    extractor = CountingUrlExtractor()
    service = service_with(extractor)
    payload = ExplorerInput(urls=["https://example.com/post"])
    extract(service, payload)

    refreshed = extract(service, payload.model_copy(update={"force_refresh": True}))

    assert refreshed.cache_status == "bypassed"
    assert extractor.calls == 2


def test_cache_failure_does_not_block_extraction() -> None:
    extractor = CountingUrlExtractor()
    service = service_with(extractor, BrokenCache())

    result = extract(service, ExplorerInput(urls=["https://example.com/post"]))

    assert result.status == "succeeded"
    assert result.cache_status == "miss"
    assert extractor.calls == 1
