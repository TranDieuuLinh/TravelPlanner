"""Golden classifier cases for the TravelPlanner Conversation Supervisor."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.config import settings
from app.integrations.llm.provider import StubLLMClient
from app.modules.plans.conversation_supervisor import (
    ConstrainedConversationSupervisor,
    ConversationSupervisorError,
)
from app.modules.plans.domain.entities import (
    BudgetLevel,
    Plan,
    PlanDay,
    PlanItem,
    PlanKind,
    PlanStatus,
    TravelIntent,
    TravelPace,
)


class FakeLLM:
    def __init__(self, *outputs: dict[str, Any]) -> None:
        self.outputs = [json.dumps(output, ensure_ascii=False) for output in outputs]
        self.calls = 0

    async def generate_structured_json(self, *_args, **_kwargs):
        self.calls += 1
        if not self.outputs:
            raise RuntimeError("fake LLM exhausted")
        return self.outputs.pop(0)


def make_plan(*, locked: bool = False) -> Plan:
    return Plan(
        id="plan-1",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Hà Nội cuối tuần",
        destination="Hà Nội",
        intent=TravelIntent(
            destination="Hà Nội",
            days=2,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        macroPlan={"title": "Hà Nội cuối tuần", "destination": "Hà Nội"},
        days=[
            PlanDay(
                day=1,
                theme="Phố cổ",
                items=[
                    PlanItem(
                        itemId="place-1",
                        name="Phố cổ Hà Nội",
                        timeWindow="morning",
                        placeType="sightseeing",
                        locked=locked,
                    ),
                    PlanItem(
                        itemId="place-2",
                        name="Bún chả Hương Liên",
                        timeWindow="lunch",
                        placeType="restaurant",
                    ),
                ],
            ),
            PlanDay(day=2, theme="Hồ Tây", items=[]),
        ],
    )


@pytest.fixture(autouse=True)
def enable_supervisor(monkeypatch):
    monkeypatch.setattr(settings, "conversation_supervisor_llm_enabled", True)


@pytest.mark.parametrize(
    ("message", "intent", "arguments"),
    [
        ("xin chào", "travel_advice", {"kind": "information", "query": "xin chào"}),
        ("bạn là ai?", "travel_advice", {"kind": "information", "query": "bạn là ai?"}),
        (
            "Việt Nam có gì đặc biệt và cần cẩn thận gì?",
            "travel_advice",
            {"kind": "information", "query": "Việt Nam có gì đặc biệt và cần cẩn thận gì?"},
        ),
        (
            "thời tiết Hà Nội hôm nay thế nào?",
            "ask_travel_information",
            {
                "kind": "information",
                "query": "thời tiết Hà Nội hôm nay thế nào?",
                "requiresFreshness": True,
            },
        ),
        (
            "lên kế hoạch Hà Nội 2 ngày",
            "create_plan",
            {"kind": "planning", "destination": "Hà Nội", "days": 2},
        ),
        (
            "làm lại lịch trình nhẹ hơn",
            "regenerate_plan",
            {"kind": "planning"},
        ),
        (
            "Tìm quán cà phê ở giữa Cầu Nhật Tân, Lăng Bác và VinUniversity",
            "find_meeting_point",
            {
                "kind": "information",
                "query": "Tìm quán cà phê ở giữa",
                "origins": ["Cầu Nhật Tân", "Lăng Bác", "VinUniversity"],
                "venueType": "cafe",
            },
        ),
    ],
)
async def test_classifier_routes_message_to_typed_intent(message, intent, arguments):
    llm = FakeLLM({"intent": intent, "confidence": 0.99, "arguments": arguments})
    plan = make_plan() if intent == "regenerate_plan" else None

    decision = await ConstrainedConversationSupervisor(llm).decide(message, plan)

    assert decision.intent == intent
    assert decision.operation is None
    assert llm.calls == 1


async def test_travel_story_follow_up_is_not_forced_into_existing_intake():
    llm = FakeLLM(
        {
            "intent": "travel_advice",
            "confidence": 0.99,
            "arguments": {
                "kind": "information",
                "query": "Việt Nam có gì đặc biệt?",
                "topic": "Việt Nam",
            },
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "tui muốn bạn kể tui nghe Việt Nam có gì đặc biệt",
        None,
        conversation_context={"currentTripIntent": {"destination": "unspecified"}},
    )

    assert decision.intent == "travel_advice"
    assert decision.information_request["topic"] == "Việt Nam"
    assert llm.calls == 1


@pytest.mark.parametrize(
    ("intent", "operation"),
    [
        ("add_place", {"type": "add_place", "day": 2, "name": "Làng Bắc"}),
        ("remove_place", {"type": "remove_place", "itemId": "place-2", "day": 1}),
        ("move_place", {"type": "move_place", "itemId": "place-1", "day": 1, "toDay": 2}),
        ("lock_item", {"type": "lock_item", "itemId": "place-1", "day": 1}),
    ],
)
async def test_mutations_use_one_typed_operation(intent, operation):
    llm = FakeLLM(
        {
            "intent": intent,
            "confidence": 0.99,
            "arguments": {"kind": "mutation", "operation": operation},
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "edit plan",
        make_plan(),
    )

    assert decision.intent == intent
    assert decision.operation["type"] == intent


async def test_ambiguous_item_request_becomes_typed_clarification():
    llm = FakeLLM(
        {
            "intent": "clarify",
            "confidence": 0.95,
            "arguments": {
                "kind": "clarification",
                "question": "Bạn muốn xóa Phố cổ hay Bún chả Hương Liên?",
                "options": [
                    {"label": "Phố cổ", "value": "Xóa Phố cổ Hà Nội"},
                    {"label": "Bún chả", "value": "Xóa Bún chả Hương Liên"},
                ],
            },
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "xóa chỗ đó",
        make_plan(),
    )

    assert decision.intent == "clarify"
    assert len(decision.clarification_options) == 2


async def test_invalid_mutation_can_be_repaired_to_clarification():
    llm = FakeLLM(
        {
            "intent": "remove_place",
            "confidence": 0.99,
            "arguments": {
                "kind": "mutation",
                "operation": {"type": "remove_place", "itemId": "missing", "day": 1},
            },
        },
        {
            "intent": "clarify",
            "confidence": 0.95,
            "arguments": {
                "kind": "clarification",
                "question": "Bạn muốn xóa địa điểm nào?",
                "options": [],
            },
        },
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "xóa chỗ đó",
        make_plan(),
    )

    assert decision.intent == "clarify"
    assert llm.calls == 2


async def test_local_stub_uses_new_classifier_contract():
    decision = await ConstrainedConversationSupervisor(StubLLMClient()).decide(
        "tôi chưa biết nên hỏi gì",
        None,
    )
    assert decision.intent == "travel_advice"
    assert decision.information_request["query"] == "tôi chưa biết nên hỏi gì"


async def test_invalid_outputs_fail_closed_after_repair():
    llm = FakeLLM(
        {"intent": "travel_advice", "confidence": 0.9},
        {"intent": "travel_advice", "confidence": 0.9},
    )
    with pytest.raises(ConversationSupervisorError):
        await ConstrainedConversationSupervisor(llm).decide("hello", None)
