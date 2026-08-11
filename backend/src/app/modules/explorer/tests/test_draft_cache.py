import asyncio

from app.modules.explorer.adapters.draft_cache import InMemoryExplorerDraftCache
from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.models import ExplorerDraft, SourceArtifact, SourceExtractionResult
from app.modules.explorer.service import ExplorerService


class CountingDraftGenerator:
    def __init__(self) -> None:
        self.source_calls = 0

    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft:
        return ExplorerDraft(inputAdm="Hanoi")

    async def from_sources(self, *, raw_prompt, sources) -> ExplorerDraft:
        self.source_calls += 1
        return ExplorerDraft(inputAdm="Hanoi")


def source_result(text: str = "Hanoi") -> SourceExtractionResult:
    return SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://example.com/hanoi",
        status="succeeded",
        artifacts=[SourceArtifact(artifactType="caption", text=text)],
    )


def service_with_cache(generator: CountingDraftGenerator) -> ExplorerService:
    unused = object()
    return ExplorerService(
        drafts=generator,
        url_extractor=unused,
        image_extractor=unused,
        snapshots=unused,
        draft_cache=InMemoryExplorerDraftCache(),
        draft_cache_namespace="test:v1",
    )


def test_source_draft_cache_skips_repeated_synthesis() -> None:
    generator = CountingDraftGenerator()
    service = service_with_cache(generator)
    payload = ExplorerInput(urls=["https://example.com/hanoi"])

    first = asyncio.run(service.source_draft(payload, [source_result()]))
    second = asyncio.run(service.source_draft(payload, [source_result()]))

    assert first == second
    assert generator.source_calls == 1


def test_force_refresh_bypasses_and_replaces_draft_cache() -> None:
    generator = CountingDraftGenerator()
    service = service_with_cache(generator)
    payload = ExplorerInput(
        urls=["https://example.com/hanoi"],
        forceRefresh=True,
    )

    asyncio.run(service.source_draft(payload, [source_result()]))
    asyncio.run(service.source_draft(payload, [source_result()]))

    assert generator.source_calls == 2
