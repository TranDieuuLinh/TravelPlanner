from dataclasses import dataclass
from typing import Any, Protocol

from app.modules.explorer.contract import ExplorerImageInput
from app.modules.explorer.models import (
    ExplorerDraft,
    MediaAnalysisResult,
    SourceArtifact,
    SourceBranch,
    SourceExtractionResult,
)
from app.modules.explorer.primary_coverage import PrimaryEvidenceCoverage


class ExplorerDraftGenerator(Protocol):
    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft: ...

    async def from_sources(
        self,
        *,
        raw_prompt: str | None,
        sources: list[SourceExtractionResult],
    ) -> ExplorerDraft: ...


class UrlSourceExtractor(Protocol):
    async def extract(
        self,
        url: str,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult: ...


class UrlSourceCache(Protocol):
    async def get(
        self, url: str, *, source_index: int
    ) -> SourceExtractionResult | None: ...

    async def save(self, url: str, result: SourceExtractionResult) -> None: ...


class ExplorerDraftCache(Protocol):
    async def get(self, cache_key: str) -> ExplorerDraft | None: ...

    async def save(self, cache_key: str, draft: ExplorerDraft) -> None: ...


class SourceExtractionCache(Protocol):
    async def get(self, cache_key: str) -> ExplorerDraft | None: ...

    async def save(self, cache_key: str, draft: ExplorerDraft) -> None: ...


class UrlMetadataClient(Protocol):
    async def extract(self, url: str) -> dict[str, Any]: ...


class PrimaryEvidenceEvaluator(Protocol):
    async def evaluate(
        self,
        artifacts: list[SourceArtifact],
        *,
        transcript_timeline_ratio: float | None = None,
        raw_prompt: str | None = None,
    ) -> PrimaryEvidenceCoverage: ...


@dataclass(frozen=True)
class DownloadedMedia:
    file_path: str
    metadata: dict[str, Any]


class UrlMediaClient(Protocol):
    async def download(self, url: str, target_dir: str) -> DownloadedMedia: ...


class MediaAnalyzer(Protocol):
    async def analyze(
        self,
        media_path: str,
        work_dir: str,
        source_url: str,
        *,
        branches: set[SourceBranch] | None = None,
    ) -> MediaAnalysisResult: ...

    async def analyze_image(self, data_base64: str, mime_type: str) -> str: ...


class WebsiteRenderer(Protocol):
    async def render(self, url: str) -> tuple[str, str]: ...


class WebsiteFetcher(Protocol):
    async def fetch(self, url: str) -> tuple[str, str]: ...


class ImageSourceExtractor(Protocol):
    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
        force_refresh: bool = False,
    ) -> SourceExtractionResult: ...


class ImageOcrCache(Protocol):
    async def get(self, cache_key: str) -> str | None: ...

    async def save(self, cache_key: str, text: str) -> None: ...


class ExplorerSnapshotRepository(Protocol):
    async def save(self, intake_id: str, snapshot_kind: str, payload: dict) -> None: ...


class TagCatalog(Protocol):
    def definitions(self) -> dict[str, list[str]]: ...

    def filter_allowed(self, values: list[str]) -> list[str]: ...


class InsightCatalog(Protocol):
    def enrich(
        self,
        *,
        budget_level: str,
        children: int,
        infants: int,
        preferences: list[str],
        avoids: list[str],
        seed: str,
    ) -> tuple[list[str], list[str]]: ...
