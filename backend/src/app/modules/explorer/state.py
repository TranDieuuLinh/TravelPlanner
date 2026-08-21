from typing import NotRequired, Required, TypedDict
from app.modules.explorer.contract import ExplorerInput, ExplorerOutput
from app.modules.explorer.models import BatchCoverage, ExplorerDraft, SourceExtractionResult
from app.shared.contracts.agent import AgentError


class ExplorerState(TypedDict):
    payload: Required[ExplorerInput]
    intake_id: NotRequired[str]
    source_results: NotRequired[list[SourceExtractionResult]]
    coverage: NotRequired[BatchCoverage]
    draft: NotRequired[ExplorerDraft]
    normalized_draft: NotRequired[ExplorerDraft]
    input_adm: NotRequired[str | None]
    adm_conflict: NotRequired[bool]
    failure: NotRequired[AgentError]
    output: NotRequired[ExplorerOutput]
