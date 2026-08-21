from datetime import UTC, datetime

from app.modules.explorer.adapters.structured_web import (
    places_from_numbered_web_headings,
)
from app.modules.explorer.contract import ExplorerImageInput, SourceNote
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import ExplorerDraft, SourceExtractionResult


class NonSemanticExplorerFallback:
    """Provider-safe fallback that never interprets natural-language intent."""

    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft:
        raise ExplorerOperationError(
            "EXPLORER_LLM_REQUIRED",
            "Explorer cần LLM để hiểu yêu cầu bằng ngôn ngữ tự nhiên.",
            retryable=True,
        )

    async def from_sources(
        self,
        *,
        raw_prompt: str | None,
        sources: list[SourceExtractionResult],
    ) -> ExplorerDraft:
        draft = ExplorerDraft()
        source_budgets = []
        for source in sources:
            draft.adm_candidates.extend(source.adm_candidates)
            draft.places.extend(source.places)
            draft.places.extend(places_from_numbered_web_headings(source))
            draft.url_notes.extend(source.notes)
            draft.short_preferences.extend(source.short_preferences)
            draft.short_avoids.extend(source.short_avoids)
            source_budgets.extend(source.budget_signals)
        if source_budgets:
            strongest = max(source_budgets, key=lambda signal: signal.confidence)
            draft.budget = strongest.budget
        return draft


class InlineImageSourceExtractor:
    """Preserve supplied OCR as evidence without inferring trip semantics."""

    async def extract(
        self,
        image: ExplorerImageInput,
        *,
        source_index: int,
        raw_prompt: str | None,
        force_refresh: bool = False,
    ) -> SourceExtractionResult:
        if not image.ocr_text:
            raise ExplorerOperationError(
                "IMAGE_OCR_FAILED",
                "OCR ảnh chưa được cấu hình cho dữ liệu ảnh thô.",
            )
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="image",
            sourceRef=image.file_name,
            status="succeeded",
            notes=[
                SourceNote(
                    summary=" ".join(image.ocr_text.split())[:500],
                    evidenceType="image_ocr",
                    observedAt=datetime.now(UTC),
                )
            ],
        )


class UnconfiguredUrlSourceExtractor:
    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        raise ExplorerOperationError(
            "SOURCE_UNAVAILABLE",
            "URL importer chưa được cấu hình trong backend scaffold.",
        )


class InMemoryExplorerSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, tuple[str, dict]] = {}

    async def save(self, intake_id: str, snapshot_kind: str, payload: dict) -> None:
        self.snapshots[intake_id] = (snapshot_kind, payload)
