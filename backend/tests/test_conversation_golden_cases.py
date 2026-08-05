"""Golden conversation cases for the VSF Travel Supervisor.

These cases test the contract around a conversational model rather than
pretending a mocked model proves model quality. They cover customer support,
intake continuity, plan mutations, confirmation gates and unsafe ambiguity.
The same case table can later be used by an offline evaluation runner with a
real LLM client.
"""

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
    ("message", "expected_intent"),
    [
        ("xin chào", "travel_advice"),
        ("bạn là ai?", "travel_advice"),
        ("bạn code được không?", "travel_advice"),
        ("bạn biết code k", "travel_advice"),
        ("bạn có thể giúp gì cho tôi", "travel_advice"),
        ("lên kế hoạch Hà Nội 2 ngày", "create_plan"),
        ("tôi muốn đi Đà Nẵng cuối tuần này", "create_plan"),
        ("tôi muốn ít nhất phải thăm làng Bắc", "create_plan"),
        ("lên plan cho tôi theo yêu cầu ở trên", "create_plan"),
    ],
)
async def test_high_signal_customer_and_intake_messages_are_not_misclassified(
    message: str,
    expected_intent: str,
):
    llm = FakeLLM()
    decision = await ConstrainedConversationSupervisor(llm).decide(message, None)

    assert decision.intent == expected_intent
    assert decision.operation is None
    assert llm.calls == 0


async def test_intake_follow_up_keeps_draft_context_signal():
    llm = FakeLLM()
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "ưu tiên món địa phương, không cần điểm sang trọng",
        None,
        conversation_context={
            "currentTripIntent": {
                "destination": "unspecified",
                "timing": {"days": 2},
                "preferences": {"mustVisitPlaces": ["Làng Bắc"]},
            }
        },
    )

    assert decision.intent == "create_plan"
    assert llm.calls == 0


async def test_affirmative_reply_to_start_invitation_enters_intake():
    llm = FakeLLM()
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "có",
        None,
        conversation_context={
            "recentMessages": [
                {
                    "role": "assistant",
                    "content": "Bạn có muốn bắt đầu lên kế hoạch cho một chuyến đi mới không?",
                }
            ]
        },
    )

    assert decision.intent == "create_plan"
    assert llm.calls == 0


@pytest.mark.parametrize(
    "message",
    [
        "địa điểm này có gì đặc biệt?",
        "tại sao bạn chọn lịch trình này?",
        "thời tiết Hà Nội hôm nay thế nào?",
        "gợi ý quán ăn gần điểm tiếp theo",
        "so sánh đi ô tô và đi bộ giúp tôi",
    ],
)
async def test_advice_with_existing_plan_does_not_mutate_plan(message: str):
    llm = FakeLLM(
        {
            "intent": "travel_advice",
            "confidence": 0.95,
            "responseText": "Mình sẽ giải thích dựa trên thông tin hiện có.",
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        message,
        make_plan(),
    )

    assert decision.intent == "travel_advice"
    assert decision.operation is None
    assert decision.requires_confirmation is False


@pytest.mark.parametrize(
    ("intent", "operation"),
    [
        ("add_place", {"type": "add_place", "day": 2, "name": "Làng Bắc"}),
        (
            "update_place",
            {
                "type": "update_place",
                "itemId": "place-1",
                "day": 1,
                "name": "Văn Miếu - Quốc Tử Giám",
            },
        ),
        (
            "remove_place",
            {"type": "remove_place", "itemId": "place-2", "day": 1},
        ),
        (
            "move_place",
            {"type": "move_place", "itemId": "place-1", "day": 1, "toDay": 2},
        ),
        (
            "lock_item",
            {"type": "lock_item", "itemId": "place-1", "day": 1},
        ),
        (
            "unlock_item",
            {"type": "unlock_item", "itemId": "place-1", "day": 1},
        ),
    ],
)
async def test_plan_mutations_return_one_safe_operation(intent: str, operation: dict[str, Any]):
    llm = FakeLLM(
        {
            "intent": intent,
            "confidence": 0.96,
            "responseText": "Mình đã hiểu yêu cầu.",
            "operations": [operation],
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        f"thực hiện {intent}",
        make_plan(),
    )

    assert decision.intent == intent
    assert decision.operation is not None
    assert decision.operation["type"] == intent
    assert len(decision.operation) >= 2


async def test_regenerate_plan_requires_confirmation():
    llm = FakeLLM(
        {
            "intent": "regenerate_plan",
            "confidence": 0.99,
            "responseText": "Mình sẽ cân đối lại lịch trình.",
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "làm lịch trình nhẹ hơn, đổi lại toàn bộ ngày 2",
        make_plan(),
    )

    assert decision.intent == "regenerate_plan"
    assert decision.requires_confirmation is True


async def test_locked_place_mutation_requires_confirmation():
    llm = FakeLLM(
        {
            "intent": "remove_place",
            "confidence": 0.99,
            "responseText": "Mình hiểu bạn muốn xóa điểm này.",
            "operations": [
                {"type": "remove_place", "itemId": "place-1", "day": 1}
            ],
        }
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "xóa Phố cổ Hà Nội",
        make_plan(locked=True),
    )

    assert decision.requires_confirmation is True


@pytest.mark.parametrize(
    "bad_output",
    [
        {
            "intent": "remove_place",
            "confidence": 0.99,
            "responseText": "Đã xóa tất cả.",
            "operations": [{"type": "remove_place", "day": 1}],
        },
        {
            "intent": "move_place",
            "confidence": 0.99,
            "responseText": "Đã chuyển.",
            "operations": [
                {"type": "move_place", "itemId": "ghost", "day": 1, "toDay": 2}
            ],
        },
        {
            "intent": "add_place",
            "confidence": 0.60,
            "responseText": "Đã thêm.",
            "operations": [{"type": "add_place", "day": 1, "name": "Một nơi"}],
        },
    ],
)
async def test_ambiguous_or_unsafe_mutation_is_rejected(bad_output: dict[str, Any]):
    llm = FakeLLM(bad_output, bad_output)
    supervisor = ConstrainedConversationSupervisor(llm)

    with pytest.raises(ConversationSupervisorError):
        await supervisor.decide("xử lý giúp tôi", make_plan())

    assert llm.calls == 2


async def test_invalid_model_output_can_be_repaired_without_unsafe_operation():
    llm = FakeLLM(
        {"intent": "remove_place", "confidence": 0.99, "responseText": "x"},
        {
            "intent": "clarify",
            "confidence": 0.95,
            "responseText": "Mình cần biết chính xác địa điểm.",
            "clarifyingQuestion": "Bạn muốn xóa Phố cổ hay Bún chả Hương Liên?",
            "options": [
                {"label": "Phố cổ", "value": "Xóa Phố cổ Hà Nội"},
                {"label": "Bún chả", "value": "Xóa Bún chả Hương Liên"},
            ],
        },
    )
    decision = await ConstrainedConversationSupervisor(llm).decide(
        "xóa chỗ đó",
        make_plan(),
    )

    assert decision.intent == "clarify"
    assert len(decision.options) == 2
    assert llm.calls == 2


async def test_local_stub_fallback_answers_without_mutating_a_plan():
    supervisor = ConstrainedConversationSupervisor(StubLLMClient())
    decision = await supervisor.decide("tôi chưa biết nên hỏi gì", make_plan())

    assert decision.intent == "clarify"
    assert decision.operation is None
    assert decision.options
