import asyncio
from uuid import uuid4

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.development import (
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    UnconfiguredUrlSourceExtractor,
)
from app.modules.explorer.models import ExplorerDraft
from app.modules.explorer.service import ExplorerService
from app.modules.supervisor.contract import ClassifierResult
from app.modules.supervisor.service import SupervisorService
from app.orchestration.root_graph import create_root_graph


class SequencedClassifier:
    def __init__(self, *results: ClassifierResult):
        self.results = list(results)

    async def classify(self, payload):
        return self.results.pop(0)


class StaticDrafts:
    def __init__(self, draft: ExplorerDraft):
        self.draft = draft

    async def from_prompt(self, raw_prompt):
        return self.draft

    async def from_sources(self, *, raw_prompt, sources):
        return self.draft


def graph_for(draft: ExplorerDraft, *decisions: ClassifierResult):
    drafts = StaticDrafts(draft)
    explorer = ExplorerService(
        drafts=drafts,
        fallback_drafts=drafts,
        url_extractor=UnconfiguredUrlSourceExtractor(),
        image_extractor=InlineImageSourceExtractor(),
        snapshots=InMemoryExplorerSnapshotRepository(),
        tag_catalog=YamlTagCatalog(),
    )
    return create_root_graph(
        explorer_service=explorer,
        supervisor_service=SupervisorService(SequencedClassifier(*decisions)),
    )


def invoke(graph, thread_id: str, message: str, turn: int):
    return asyncio.run(
        graph.ainvoke(
            {"request_id": f"review-{turn}", "message": message},
            config={"configurable": {"thread_id": thread_id}},
        )
    )


def decision(*, patch=None) -> ClassifierResult:
    return ClassifierResult(
        route="explorer",
        confidence=0.99,
        reason="Structured LLM planning decision.",
        trip_context_patch=patch,
    )


def test_missing_destination_then_defaults_then_acceptance() -> None:
    graph = graph_for(
        ExplorerDraft(days=2),
        decision(),
        decision(patch={"inputADM": {"operation": "set", "value": "Hà Nội"}}),
        decision(patch={}),
    )
    thread_id = str(uuid4())

    missing = invoke(graph, thread_id, "Lập kế hoạch 2 ngày", 1)
    assert missing["explorer_review"]["kind"] == "missing_fields"

    defaults = invoke(graph, thread_id, "Hà Nội", 2)
    assert defaults["explorer_review"]["kind"] == "defaults_proposed"
    assert defaults["explorer_output"].days == 2

    accepted = invoke(graph, thread_id, "OK", 3)
    assert accepted["explorer_review"]["kind"] == "ready_for_execution"
    assert accepted.get("pending_explorer_review") is None


def test_colloquial_luxury_reply_updates_only_budget() -> None:
    graph = graph_for(
        ExplorerDraft(inputAdm="Hanoi"),
        decision(),
        decision(patch={
            "budget": {
                "operation": "set",
                "value": {"level": "high", "currency": "VND"},
            }
        }),
    )
    thread_id = str(uuid4())
    invoke(graph, thread_id, "lên plan Hà Nội", 1)

    result = invoke(
        graph,
        thread_id,
        "tui muốn đi giàu sang mắc nhất vô lên plan dì",
        2,
    )

    assert result["explorer_output"].input_adm == "Hanoi"
    assert result["explorer_output"].budget.level == "high"
    assert result["explorer_review"]["kind"] == "ready_for_execution"


def test_fully_explicit_structured_draft_skips_default_review() -> None:
    graph = graph_for(
        ExplorerDraft.model_validate({
            "inputAdm": "Hanoi",
            "days": 4,
            "people": {"adults": 3},
            "peopleExplicit": True,
            "preferencesExplicit": True,
            "shortPreferences": ["Văn hóa"],
            "budget": {
                "level": "medium",
                "targetAmount": 6_000_000,
                "source": "raw_prompt",
            },
        }),
        decision(),
    )

    result = invoke(
        graph,
        str(uuid4()),
        "Lập kế hoạch Hà Nội 4 ngày cho 3 người, budget 6 triệu/người",
        1,
    )

    assert result["explorer_review"]["kind"] == "ready_for_execution"
