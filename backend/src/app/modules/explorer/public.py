from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerImageInput,
    ExplorerInput,
    ExplorerOutput,
    ExplorerPeople,
    ExplorerPlace,
    PlaceSource,
    RequestedItem,
    SourceNote,
)
from app.modules.explorer.adapters import (
    GeminiExplorerDraftGenerator,
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    PythonYtDlpClient,
    RuleBasedExplorerDraftGenerator,
    YtDlpTikTokUrlSourceExtractor,
)
from app.modules.explorer.graph import build_explorer_graph
from app.modules.explorer.service import ExplorerService
from app.shared.llm import LlmClient


def create_explorer_service(
    *,
    draft_provider: str = "rules",
    llm_client: LlmClient | None = None,
    max_output_tokens: int = 1600,
    url_timeout_seconds: float = 30,
    ytdlp_cookie_file: str | None = None,
) -> ExplorerService:
    rules = RuleBasedExplorerDraftGenerator()
    if draft_provider == "gemini":
        if llm_client is None:
            raise ValueError("Gemini Explorer requires an LlmClient.")
        drafts = GeminiExplorerDraftGenerator(
            llm_client, max_output_tokens=max_output_tokens
        )
    elif draft_provider == "rules":
        drafts = rules
    else:
        raise ValueError(f"Unsupported Explorer draft provider: {draft_provider}")
    return ExplorerService(
        drafts=drafts,
        url_extractor=YtDlpTikTokUrlSourceExtractor(
            PythonYtDlpClient(
                timeout_seconds=url_timeout_seconds,
                cookie_file=ytdlp_cookie_file,
            ),
            rules,
        ),
        image_extractor=InlineImageSourceExtractor(rules),
        snapshots=InMemoryExplorerSnapshotRepository(),
    )


__all__ = [
    "ExplorerBudget", "ExplorerImageInput", "ExplorerInput", "ExplorerOutput",
    "ExplorerPeople", "ExplorerPlace", "PlaceSource", "RequestedItem", "SourceNote",
    "build_explorer_graph",
    "create_explorer_service",
]
