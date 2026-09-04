import asyncio

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.development import (
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    UnconfiguredUrlSourceExtractor,
)
from app.modules.explorer.adapters.user_insights import YamlInsightCatalog
from app.modules.explorer.models import ExplorerDraft
from app.modules.explorer.public import build_explorer_graph
from app.modules.explorer.service import ExplorerService
from app.modules.place_checker.tests.test_pipeline_output import pipeline
from app.orchestration.nodes import RootNodes


class StructuredPreferenceDrafts:
    async def from_prompt(self, raw_prompt):
        return ExplorerDraft.model_validate({
            "inputAdm": "Hà Nội",
            "days": 1,
            "preferencesExplicit": True,
            "shortPreferences": ["Văn hóa"],
            "inputItems": [{
                "name": "phở",
                "itemType": "food",
                "action": "eat",
                "evidence": "Muốn ăn phở",
                "confidence": 0.99,
            }],
        })

    async def from_sources(self, *, raw_prompt, sources):
        return ExplorerDraft()


def explorer_service() -> ExplorerService:
    drafts = StructuredPreferenceDrafts()
    tags = YamlTagCatalog()
    return ExplorerService(
        drafts=drafts,
        fallback_drafts=drafts,
        url_extractor=UnconfiguredUrlSourceExtractor(),
        image_extractor=InlineImageSourceExtractor(),
        snapshots=InMemoryExplorerSnapshotRepository(),
        tag_catalog=tags,
        insight_catalog=YamlInsightCatalog(tags),
    )


def test_prompt_preferences_reach_place_checker_before_pool_gate() -> None:
    explorer = asyncio.run(
        build_explorer_graph(explorer_service()).ainvoke(
            {"payload": {"rawPrompt": ("Đi Hà Nội 1 ngày, thích văn hóa. Muốn ăn phở")}}
        )
    )["output"]
    nodes = RootNodes(place_checker_pipeline=pipeline())

    update = asyncio.run(
        nodes.run_place_checker(
            {
                "request_id": "intake-preferences-flow",
                "explorer_output": explorer,
                "warnings": [],
            }
        )
    )

    output = update["place_output"]
    pho = next(item for item in output.resolved_items if item.selected)
    assert output.trip_context.preferences == [
        "văn hóa",
        "giá rẻ",
        "địa phương",
        "ẩm thực",
        "thiên nhiên",
        "biển",
        "núi",
        "cảnh quan",
    ]
    assert output.trip_context.avoids == ["sang trọng"]
    assert pho.selected.place_id == "kg:pho"
    assert output.status.value == "blocked"
    assert "planner_input" not in update
