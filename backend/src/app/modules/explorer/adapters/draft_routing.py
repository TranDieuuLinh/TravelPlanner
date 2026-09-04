from app.modules.explorer.models import ExplorerDraft, SourceExtractionResult


class RoutedExplorerDraftGenerator:
    """Route prompt and source synthesis to their configured structured providers."""

    def __init__(self, *, prompt_generator, source_generator) -> None:
        self.prompt_generator = prompt_generator
        self.source_generator = source_generator

    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft:
        return await self.prompt_generator.from_prompt(raw_prompt)

    async def from_sources(
        self, *, raw_prompt: str | None, sources: list[SourceExtractionResult]
    ) -> ExplorerDraft:
        return await self.source_generator.from_sources(
            raw_prompt=raw_prompt, sources=sources
        )
