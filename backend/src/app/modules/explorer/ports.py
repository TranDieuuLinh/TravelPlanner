from typing import Any, Protocol

from app.modules.explorer.contract import ExplorerImageInput
from app.modules.explorer.models import ExplorerDraft, SourceExtractionResult


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


class UrlMetadataClient(Protocol):
    async def extract(self, url: str) -> dict[str, Any]: ...


class ImageSourceExtractor(Protocol):
    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult: ...


class ExplorerSnapshotRepository(Protocol):
    async def save(self, intake_id: str, snapshot_kind: str, payload: dict) -> None: ...
