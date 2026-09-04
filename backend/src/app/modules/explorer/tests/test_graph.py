import asyncio
from datetime import date, datetime, timedelta

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.development import (
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    UnconfiguredUrlSourceExtractor,
)
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import ExplorerDraft
from app.modules.explorer.public import build_explorer_graph
from app.modules.explorer.retry import run_with_one_retry
from app.modules.explorer.service import ExplorerService


class StaticStructuredDrafts:
    def __init__(self, draft: ExplorerDraft):
        self.draft = draft

    async def from_prompt(self, raw_prompt: str) -> ExplorerDraft:
        return self.draft

    async def from_sources(self, *, raw_prompt, sources) -> ExplorerDraft:
        return self.draft


def invoke(payload: dict, draft: ExplorerDraft | None = None):
    drafts = StaticStructuredDrafts(draft or ExplorerDraft())
    service = ExplorerService(
        drafts=drafts,
        fallback_drafts=drafts,
        url_extractor=UnconfiguredUrlSourceExtractor(),
        image_extractor=InlineImageSourceExtractor(),
        snapshots=InMemoryExplorerSnapshotRepository(),
        tag_catalog=YamlTagCatalog(),
    )
    graph = build_explorer_graph(service)
    return asyncio.run(graph.ainvoke({"payload": payload}))["output"]


def test_structured_llm_draft_supplies_trip_fields_without_prompt_regex() -> None:
    output = invoke(
        {"rawPrompt": "Lập kế hoạch ở Huế trong 4 ngày cho 3 người"},
        ExplorerDraft.model_validate({
            "inputAdm": "Huế",
            "days": 4,
            "startDate": "2026-09-01",
            "people": {"adults": 3},
            "peopleExplicit": True,
            "preferencesExplicit": True,
            "shortPreferences": ["Văn hóa"],
            "budget": {"level": "medium", "source": "raw_prompt"},
        }),
    )

    assert output.status == "ready"
    assert output.input_adm == "Huế"
    assert output.days == 4
    assert output.people.adults == 3
    assert output.start_date == date(2026, 9, 1)
    assert output.defaulted_fields == []


def test_missing_structured_fields_use_explicit_defaults() -> None:
    output = invoke(
        {"rawPrompt": "Lập kế hoạch Hà Nội"},
        ExplorerDraft(inputAdm="Hanoi"),
    )

    assert output.days == 3
    assert output.start_date == datetime.now().astimezone().date() + timedelta(days=1)
    assert output.people.adults == 2
    assert output.defaulted_fields == [
        "days",
        "budget",
        "people",
        "shortPreferences",
    ]


def test_luxury_intent_arrives_as_high_budget_without_rewriting_destination() -> None:
    output = invoke(
        {"rawPrompt": "tui muốn đi giàu sang mắc nhất vô lên plan dì"},
        ExplorerDraft.model_validate({
            "inputAdm": "Hanoi",
            "budget": {"level": "high", "source": "raw_prompt"},
        }),
    )

    assert output.input_adm == "Hanoi"
    assert output.budget.level == "high"


def test_missing_adm_uses_clarification_path() -> None:
    output = invoke(
        {"rawPrompt": "Lập kế hoạch nhưng chưa chọn điểm đến"},
        ExplorerDraft(days=3),
    )

    assert output.status == "clarification"
    assert output.input_adm is None
    assert output.clarification_question == "Bạn muốn đi tỉnh hoặc thành phố nào?"


def test_unconfigured_url_returns_failure_after_retry_policy() -> None:
    output = invoke({"urls": ["https://example.com/video"]})

    assert output.status == "error"
    assert output.error.code == "SOURCE_UNAVAILABLE"


def test_retryable_operation_runs_at_most_twice() -> None:
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ExplorerOperationError("TEMPORARY", "temporary", retryable=True)

    try:
        asyncio.run(run_with_one_retry(operation))
    except ExplorerOperationError:
        pass

    assert attempts == 2
