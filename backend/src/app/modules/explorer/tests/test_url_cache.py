import asyncio

from app.modules.explorer.adapters.postgres import asyncpg_dsn
from app.modules.explorer.adapters.url_cache import (
    InMemoryUrlSourceCache,
    _decode_artifacts,
    _decode_coverage,
    canonicalize_source_url,
)
from app.modules.explorer.contract import ExplorerInput, ExplorerPlace, PlaceSource
from app.modules.explorer.models import (
    ExplorerDraft,
    SourceArtifact,
    SourceExtractionResult,
)
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
            artifacts=[
                SourceArtifact(
                    artifactType="caption",
                    text="Huế",
                    sourceUrl=url,
                    language="vi",
                )
            ],
        )


class UnusedDependency:
    pass


class BrokenCache:
    async def get(self, url, *, source_index):
        raise RuntimeError("cache unavailable")

    async def save(self, url, result):
        raise RuntimeError("cache unavailable")


class SlowUrlExtractor:
    async def extract(self, url, *, source_index, raw_prompt):
        await asyncio.sleep(60)


class SlowDraftGenerator:
    async def from_sources(self, *, raw_prompt, sources):
        await asyncio.sleep(60)

    async def from_prompt(self, raw_prompt):
        await asyncio.sleep(60)


class FallbackDraftGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def from_sources(self, *, raw_prompt, sources):
        self.calls += 1
        return ExplorerDraft(
            input_adm="Hanoi",
            places=[
                ExplorerPlace(
                    name="Structured Place",
                    sourcePlaces=[
                        PlaceSource(
                            origin="url",
                            evidenceType="web_text",
                            sourceUrl=sources[0].source_ref,
                            evidence="## 1. Structured Place",
                        )
                    ],
                )
            ],
        )


class FastDraftGenerator:
    async def from_sources(self, *, raw_prompt, sources):
        return ExplorerDraft(
            places=[
                ExplorerPlace(
                    name="Semantic Place",
                    sourcePlaces=[
                        PlaceSource(
                            origin="url",
                            evidenceType="caption",
                            sourceUrl=sources[0].source_ref,
                            evidence="Semantic Place",
                        )
                    ],
                )
            ]
        )


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
    assert (
        canonicalize_source_url("HTTPS://youtu.be/abc123/?utm_source=x&t=7#caption")
        == "https://www.youtube.com/watch?v=abc123&t=7"
    )


def test_canonical_url_removes_all_tiktok_query_parameters() -> None:
    assert (
        canonicalize_source_url(
            "https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510"
            "?q=things%20to%20do%20in%20Hanoi&t=1786464699496"
        )
        == "https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510"
    )


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
        "9",
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

    extract(service, ExplorerInput(urls=["https://example.com/post?utm_source=x"]))
    extract(service, ExplorerInput(urls=["https://example.com/post"]))

    assert extractor.calls == 1


def test_force_refresh_bypasses_hit_and_replaces_cache() -> None:
    extractor = CountingUrlExtractor()
    service = service_with(extractor)
    payload = ExplorerInput(urls=["https://example.com/post"])
    extract(service, payload)

    extract(service, payload.model_copy(update={"force_refresh": True}))

    assert extractor.calls == 2


def test_cache_failure_does_not_block_extraction() -> None:
    extractor = CountingUrlExtractor()
    service = service_with(extractor, BrokenCache())

    result = extract(service, ExplorerInput(urls=["https://example.com/post"]))

    assert result.status == "succeeded"
    assert extractor.calls == 1


def test_source_extraction_has_one_wall_clock_budget_including_retries() -> None:
    unused = UnusedDependency()
    service = ExplorerService(
        drafts=unused,
        url_extractor=SlowUrlExtractor(),
        image_extractor=unused,
        snapshots=unused,
        source_extraction_timeout_seconds=0.01,
    )

    result = extract(
        service,
        ExplorerInput(
            urls=["https://example.com/slow"],
            forceRefresh=True,
        ),
    )

    assert result.status == "failed_retryable"
    assert result.error is not None
    assert result.error.code == "SOURCE_EXTRACTION_TIMEOUT"


def test_source_synthesis_timeout_uses_uncached_deterministic_fallback() -> None:
    unused = UnusedDependency()
    fallback = FallbackDraftGenerator()
    service = ExplorerService(
        drafts=SlowDraftGenerator(),
        fallback_drafts=fallback,
        url_extractor=unused,
        image_extractor=unused,
        snapshots=unused,
        source_synthesis_timeout_seconds=0.01,
    )
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/slow",
        status="succeeded",
        artifacts=[
            SourceArtifact(
                artifactType="caption",
                text="Hà Nội",
                sourceUrl="https://example.com/slow",
            )
        ],
    )

    draft = asyncio.run(
        service.source_draft(
            ExplorerInput(rawPrompt="Đi Hà Nội", forceRefresh=True),
            [source],
        )
    )

    assert draft.input_adm == "Hanoi"
    assert fallback.calls == 1
    assert source.status == "partial"
    assert source.synthesis_coverage_ratio == 0


def test_successful_semantic_synthesis_also_keeps_structured_web_places() -> None:
    unused = UnusedDependency()
    fallback = FallbackDraftGenerator()
    service = ExplorerService(
        drafts=FastDraftGenerator(),
        fallback_drafts=fallback,
        url_extractor=unused,
        image_extractor=unused,
        snapshots=unused,
    )
    source = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/guide",
        status="succeeded",
    )

    draft = asyncio.run(
        service.source_draft(ExplorerInput(urls=[source.source_ref]), [source])
    )

    assert [place.name for place in draft.places] == [
        "Semantic Place",
        "Structured Place",
    ]
    assert fallback.calls == 1
