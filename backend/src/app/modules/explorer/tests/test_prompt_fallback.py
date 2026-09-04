import asyncio

import pytest

from app.modules.explorer.adapters.development import NonSemanticExplorerFallback
from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.service import ExplorerService


class FailingPromptGenerator:
    async def from_prompt(self, raw_prompt: str):
        raise RuntimeError("provider unavailable")

    async def from_sources(self, *, raw_prompt, sources):
        raise RuntimeError("provider unavailable")


def test_prompt_provider_failure_never_falls_back_to_semantic_rules():
    service = ExplorerService(
        drafts=FailingPromptGenerator(),
        fallback_drafts=NonSemanticExplorerFallback(),
        url_extractor=object(),
        image_extractor=object(),
        snapshots=object(),
    )

    prepared = service.prepare(ExplorerInput(raw_prompt="đi Hà Nội 2 ngày"))
    with pytest.raises(ExplorerOperationError, match="cần LLM"):
        asyncio.run(service.prompt_draft(prepared["payload"].raw_prompt))
