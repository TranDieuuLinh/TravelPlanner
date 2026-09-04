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


class StaticDrafts:
    def __init__(self, draft: ExplorerDraft):
        self.draft = draft

    async def from_prompt(self, raw_prompt):
        return self.draft

    async def from_sources(self, *, raw_prompt, sources):
        return self.draft


class SequencedClassifier:
    def __init__(self, *results: ClassifierResult):
        self.results = list(results)

    async def classify(self, payload):
        return self.results.pop(0)


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


def route(name: str, *, response=None, source_action=None) -> ClassifierResult:
    return ClassifierResult(
        route=name,
        confidence=0.99,
        reason="Structured test classification.",
        response=response,
        source_action=source_action,
    )


def test_planning_flow_reviews_defaults_before_place_checker() -> None:
    graph = graph_for(
        ExplorerDraft(inputAdm="Đà Nẵng", days=2),
        route("explorer"),
    )
    thread_id = str(uuid4())

    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "request-1",
                "message": "Lập kế hoạch ở Đà Nẵng trong 2 ngày, tham quan Cầu Rồng",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    )

    assert result["decision"].route == "explorer"
    assert result.get("itinerary") is None
    assert result["explorer_review"]["kind"] == "defaults_proposed"
    assert result.get("place_output") is None
    assert "giá trị mặc định" in result["response"]


def test_planning_flow_returns_clarification() -> None:
    graph = graph_for(ExplorerDraft(days=2), route("explorer"))

    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "request-2", "message": "Lập kế hoạch 2 ngày"},
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result.get("itinerary") is None
    assert result["clarification_question"] == "Bạn muốn đi tỉnh hoặc thành phố nào?"
    assert result["explorer_review"]["kind"] == "missing_fields"
    assert result.get("place_output") is None


def test_image_without_prompt_routes_to_explorer() -> None:
    graph = graph_for(ExplorerDraft(inputAdm="Huế"), route("explorer"))
    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "request-image",
                "message": "",
                "images": [
                    {
                        "fileName": "capture.png",
                        "mimeType": "image/png",
                        "ocrText": "Du lịch ở Huế, tham quan Đại Nội",
                    }
                ],
            },
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result["decision"].route == "explorer"
    assert result["explorer_output"].input_adm == "Huế"


def test_source_summary_stops_before_default_review_and_place_checker() -> None:
    graph = graph_for(
        ExplorerDraft(inputAdm="Huế"),
        route("explorer", source_action="summarize_source"),
    )
    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "request-summary",
                "message": "Tóm tắt nội dung liên kết này",
                "images": [
                    {
                        "fileName": "capture.png",
                        "mimeType": "image/png",
                        "ocrText": "Du lịch ở Huế, tham quan Đại Nội",
                    }
                ],
            },
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result["decision"].source_action == "summarize_source"
    assert "Huế" in result["response"]
    assert result.get("place_output") is None
    assert result.get("pending_explorer_review") is None


def test_same_thread_keeps_user_context_for_follow_up_routing() -> None:
    graph = graph_for(
        ExplorerDraft(),
        route("information_finder"),
        route("information_finder"),
    )
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    asyncio.run(
        graph.ainvoke(
            {"request_id": "context-1", "message": "Tôi muốn biết về Hải Phòng."},
            config=config,
        )
    )
    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "context-2", "message": "Còn chỗ này thì sao?"},
            config=config,
        )
    )

    assert result["decision"].route == "information_finder"
    assert result.get("itinerary") is None


def test_same_thread_routes_english_destination_follow_up_to_information() -> None:
    graph = graph_for(
        ExplorerDraft(),
        route("information_finder"),
        route("information_finder"),
    )
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    asyncio.run(
        graph.ainvoke(
            {
                "request_id": "context-info-1",
                "message": "Tôi muốn biết thêm về Hà Nội.",
            },
            config=config,
        )
    )
    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "context-info-2", "message": "Hoàn Kiếm Lake thì sao?"},
            config=config,
        )
    )

    assert result["decision"].route == "information_finder"
