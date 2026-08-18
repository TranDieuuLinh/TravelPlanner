import asyncio

from app.modules.explorer.adapters.development import RuleBasedExplorerDraftGenerator
from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.service import ExplorerService


class FailingPromptGenerator:
    async def from_prompt(self, raw_prompt: str):
        raise RuntimeError("provider unavailable")

    async def from_sources(self, *, raw_prompt, sources):
        raise RuntimeError("provider unavailable")


def test_prompt_only_request_falls_back_when_semantic_provider_fails():
    service = ExplorerService(
        drafts=FailingPromptGenerator(),
        fallback_drafts=RuleBasedExplorerDraftGenerator(),
        url_extractor=object(),
        image_extractor=object(),
        snapshots=object(),
    )

    prepared = service.prepare(ExplorerInput(raw_prompt="đi Hà Nội 2 ngày"))
    draft = asyncio.run(service.prompt_draft(prepared["payload"].raw_prompt))

    assert draft.input_adm == "Hanoi"
