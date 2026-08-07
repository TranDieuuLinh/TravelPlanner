import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.integrations.llm.base import GroundedStructuredResult, GroundingSource
from app.modules.plans.conversation_agents import ConversationAgentContext
from app.modules.plans.information_finder import (
    InformationCandidate,
    InformationFinderAgent,
    InformationResult,
)


class FakeReader:
    def __init__(self, result: InformationResult):
        self.result = result
        self.calls = []

    async def search(self, query, destination, top_k, filters=None):
        self.calls.append((query, destination, top_k, filters))
        return self.result


class FakeLLM:
    def __init__(self, answer="Thông tin hữu ích", *, grounded=False):
        self.answer = answer
        self.grounded = grounded
        self.calls = []

    async def generate_structured_json(
        self, system_prompt, user_payload, *, response_schema
    ):
        self.calls.append(("structured", json.loads(user_payload), response_schema))
        return json.dumps({"answer": self.answer}, ensure_ascii=False)

    async def generate_grounded_structured_json(
        self, system_prompt, user_payload, *, response_schema
    ):
        self.calls.append(("grounded", json.loads(user_payload), response_schema))
        return GroundedStructuredResult(
            text=json.dumps({"answer": self.answer}, ensure_ascii=False),
            sources=(GroundingSource(title="Official source", uri="https://example.test"),),
        )


def candidate():
    return InformationCandidate(
        candidateId="maps:cafe-1",
        placeId="cafe-1",
        source="external_provider",
        sourceRefs=["maps:cafe-1"],
        confidence=0.5,
        fetchedAt=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )


def context(
    content="cafe",
    *,
    decision_intent="ask_place",
    decision_message=None,
    **data,
):
    chat = SimpleNamespace(destination="Hanoi", revision=4)
    turn = SimpleNamespace(content=content)
    decision = SimpleNamespace(
        intent=decision_intent,
        message=decision_message,
        options=(),
    )
    return ConversationAgentContext(chat, turn, decision, None, data=data)


def test_travel_advice_is_answered_by_information_finder_llm():
    reader = FakeReader(InformationResult(kind="empty", message="unused"))
    llm = FakeLLM("Chào bạn! Mình có thể tư vấn du lịch.")
    response = asyncio.run(
        InformationFinderAgent(reader, llm).run(
            context(
                "xin chào",
                decision_intent="travel_advice",
            )
        )
    )

    assert response.message == "Chào bạn! Mình có thể tư vấn du lịch."
    assert response.blocks == [
        {"type": "text", "text": "Chào bạn! Mình có thể tư vấn du lịch."}
    ]
    assert llm.calls[0][0] == "structured"
    assert reader.calls == []


def test_place_query_calls_reader_and_returns_candidate_blocks():
    reader = FakeReader(InformationResult(kind="candidates", message="Choose", candidates=[candidate()], needsUserChoice=True))
    response = asyncio.run(InformationFinderAgent(reader).run(context("find cafes")))

    assert reader.calls == [("find cafes", "Hanoi", 5, None)]
    assert {block["type"] for block in response.blocks} >= {"candidateList", "optionSelector"}
    assert response.result.candidates[0].source_refs == ["maps:cafe-1"]


def test_ambiguous_query_clarifies_without_reading():
    reader = FakeReader(InformationResult(kind="empty", message="unused"))
    response = asyncio.run(InformationFinderAgent(reader).run(context("địa điểm này")))

    assert reader.calls == []
    assert response.blocks[0]["type"] == "text"


def test_travel_information_without_source_is_unknown_or_stale():
    response = asyncio.run(InformationFinderAgent().run(
        context("weather tomorrow", information_intent="ask_travel_information")
    ))

    warning = next(block for block in response.blocks if block["type"] == "warning")
    assert warning["code"] == "GROUNDED_LLM_UNAVAILABLE"


def test_travel_information_uses_grounded_llm_and_returns_sources():
    llm = FakeLLM("Ngày mai có khả năng mưa.")
    response = asyncio.run(
        InformationFinderAgent(llm=llm).run(
            context("weather tomorrow", information_intent="ask_travel_information")
        )
    )

    assert response.message == "Ngày mai có khả năng mưa."
    assert llm.calls[0][0] == "grounded"
    assert any(block["type"] == "sources" for block in response.blocks)


def test_explain_plan_uses_sources_and_does_not_change_revision():
    item = SimpleNamespace(
        item_id="item-1",
        name="Cafe",
        time_window="morning",
        place_type="cafe",
        source_refs=["https://example.test/plan"],
    )
    plan = SimpleNamespace(title="Trip", destination="Hanoi", days=[SimpleNamespace(day=1, theme="Food", items=[item])])
    current = context("why", information_intent="explain_plan")
    current.plan = plan
    before = current.chat.revision

    llm = FakeLLM("Quán cà phê nằm buổi sáng vì phù hợp chủ đề ẩm thực.")
    response = asyncio.run(InformationFinderAgent(llm=llm).run(current))

    assert any(block["type"] == "sourceRefs" for block in response.blocks)
    assert llm.calls[0][1]["currentPlan"]["destination"] == "Hanoi"
    assert current.chat.revision == before


def test_provider_warning_is_rendered():
    result = InformationResult(kind="empty", message="No places", warnings=["provider_search_failed:maps"])
    response = asyncio.run(InformationFinderAgent(FakeReader(result)).run(context("cafes")))

    assert any(block["type"] == "warning" for block in response.blocks)
