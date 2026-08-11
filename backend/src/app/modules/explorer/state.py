from typing import TypedDict

from app.modules.explorer.contract import ExplorerInput, ExplorerOutput
from app.modules.explorer.models import BatchCoverage, ExplorerDraft, SourceExtractionResult
from app.shared.contracts.agent import AgentError


class ExplorerState(TypedDict, total=False):
    payload: ExplorerInput
    intake_id: str
    prompt_days: int | None
    source_results: list[SourceExtractionResult]
    coverage: BatchCoverage
    draft: ExplorerDraft
    normalized_draft: ExplorerDraft
    input_adm: str | None
    adm_conflict: bool
    failure: AgentError
    output: ExplorerOutput
