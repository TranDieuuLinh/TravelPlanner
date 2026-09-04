import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.information_finder.public import (
    AnswerMetadata,
    InformationFinderOutput,
    SourceReference,
)
from app.modules.supervisor.contract import ClassifierResult
from app.modules.supervisor.service import SupervisorService
from app.orchestration.nodes import RootNodes
from app.orchestration.root_graph import create_root_graph


class InformationClassifier:
    async def classify(self, payload):
        return ClassifierResult(
            route="information_finder",
            confidence=1.0,
            reason="Travel information request.",
        )


class GeminiComposerSpy:
    def __init__(self):
        self.calls = 0

    async def compose(self, payload):
        self.calls += 1
        raise AssertionError("final response composer must not be called")


class FinalResponseFinder:
    entity_resolver = None

    async def find(self, query, *, force_refresh=False):
        return InformationFinderOutput(
            answer="Bảo tàng mở cửa từ 08:00 đến 17:00. [1]",
            sources=[
                SourceReference(
                    source_id="museum-source",
                    title="Museum hours",
                    url="https://example.test/museum",
                    updated_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
                    date_kind="source_updated_at",
                )
            ],
            warnings=["Nguồn đang chờ admin review."],
            metadata=AnswerMetadata(
                generation_mode="structured",
                validation_status="citation_validated",
                confidence="medium",
                cited_source_count=1,
            ),
        )


def test_information_route_returns_finder_output_without_finish_gemini_call():
    composer = GeminiComposerSpy()
    graph = create_root_graph(
        checkpointer=False,
        information_finder_service=FinalResponseFinder(),
        supervisor_service=SupervisorService(
            InformationClassifier(),
            composer,
        ),
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "finder-final-response",
                "message": "Bảo tàng mở cửa lúc mấy giờ?",
            },
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result["response"] == "Bảo tàng mở cửa từ 08:00 đến 17:00. [1]"
    assert result["warnings"] == ["Nguồn đang chờ admin review."]
    assert result["information_output"].sources[0].source_id == "museum-source"
    assert composer.calls == 0


def test_finish_is_deterministic_and_does_not_call_composer():
    composer = GeminiComposerSpy()
    nodes = RootNodes(
        supervisor_service=SupervisorService(InformationClassifier(), composer)
    )

    result = asyncio.run(nodes.finish({"response": "Đã hoàn tất."}))

    assert result == {"response": "Đã hoàn tất."}
    assert composer.calls == 0
