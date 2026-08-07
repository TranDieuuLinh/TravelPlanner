"""Contract and safety tests for the classifier-only Conversation Supervisor."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.modules.plans.conversation_supervisor import (
    ClarificationArguments,
    ConstrainedConversationSupervisor,
    ConversationSupervisorError,
    InformationArguments,
    MutationArguments,
    PlanningArguments,
    SupervisorOutput,
    _find_plan_item,
    _has_plan_day,
    _plan_summary,
    _validated_decision,
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


def _make_plan(*, locked: bool = False) -> Plan:
    return Plan(
        id="plan-1",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Trip",
        destination="Đà Lạt",
        intent=TravelIntent(
            destination="Đà Lạt",
            days=2,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        macroPlan={"title": "Trip", "destination": "Đà Lạt"},
        days=[
            PlanDay(
                day=1,
                theme="Day 1",
                items=[
                    PlanItem(
                        itemId="place-1",
                        name="Place 1",
                        timeWindow="morning",
                        placeType="restaurant",
                        timelineCategory="food",
                        locked=locked,
                    )
                ],
            ),
            PlanDay(day=2, theme="Day 2", items=[]),
        ],
    )


@pytest.fixture(autouse=True)
def _enable_supervisor(monkeypatch):
    monkeypatch.setattr(settings, "conversation_supervisor_llm_enabled", True)


class FakeLLM:
    def __init__(self, *outputs: dict[str, Any] | str) -> None:
        self.outputs = [
            output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
            for output in outputs
        ]
        self.calls = 0
        self.last_payload: dict[str, Any] | None = None
        self.last_schema: dict[str, Any] | None = None

    async def generate_structured_json(
        self, system_prompt, user_payload, *, response_schema
    ):
        self.calls += 1
        self.last_payload = json.loads(user_payload)
        self.last_schema = response_schema
        if not self.outputs:
            raise RuntimeError("fake LLM exhausted")
        return self.outputs.pop(0)


def _output(intent: str, arguments: dict[str, Any], **overrides: Any) -> SupervisorOutput:
    payload = {"intent": intent, "confidence": 0.95, "arguments": arguments}
    payload.update(overrides)
    return SupervisorOutput.model_validate(payload)


class TestSupervisorSchema:
    def test_classifier_schema_has_only_decision_fields(self):
        schema = SupervisorOutput.model_json_schema(by_alias=True)
        assert set(schema["properties"]) == {"intent", "confidence", "arguments"}
        assert "responseText" not in schema["properties"]
        assert "agent" not in schema["properties"]

    def test_information_arguments(self):
        output = _output(
            "travel_advice",
            {"kind": "information", "query": "Việt Nam có gì đặc biệt?"},
        )
        assert isinstance(output.arguments, InformationArguments)
        assert output.arguments.query == "Việt Nam có gì đặc biệt?"

    def test_planning_arguments(self):
        output = _output(
            "create_plan",
            {"kind": "planning", "destination": "Hà Nội", "days": 3},
        )
        assert isinstance(output.arguments, PlanningArguments)
        assert output.arguments.days == 3

    def test_mutation_arguments(self):
        output = _output(
            "add_place",
            {
                "kind": "mutation",
                "operation": {"type": "add_place", "day": 1, "name": "Cafe"},
            },
        )
        assert isinstance(output.arguments, MutationArguments)

    def test_clarification_arguments(self):
        output = _output(
            "clarify",
            {
                "kind": "clarification",
                "question": "Bạn muốn chuyến mới hay sửa chuyến này?",
                "options": [{"label": "Chuyến mới", "value": "Tạo chuyến mới"}],
            },
        )
        assert isinstance(output.arguments, ClarificationArguments)

    @pytest.mark.parametrize(
        ("intent", "arguments"),
        [
            ("travel_advice", {"kind": "planning"}),
            ("create_plan", {"kind": "information", "query": "x"}),
            ("clarify", {"kind": "command"}),
            ("undo", {"kind": "mutation", "operation": {"type": "add_place", "day": 1, "name": "x"}}),
        ],
    )
    def test_arguments_kind_must_match_intent(self, intent, arguments):
        with pytest.raises(ValidationError):
            _output(intent, arguments)

    def test_operation_type_must_match_mutation_intent(self):
        with pytest.raises(ValidationError, match="operation type must match"):
            _output(
                "remove_place",
                {
                    "kind": "mutation",
                    "operation": {"type": "lock_item", "itemId": "place-1", "day": 1},
                },
            )

    def test_freshness_is_limited_to_current_information(self):
        with pytest.raises(ValidationError, match="requiresFreshness"):
            _output(
                "travel_advice",
                {
                    "kind": "information",
                    "query": "Việt Nam có gì đặc biệt?",
                    "requiresFreshness": True,
                },
            )

    def test_extra_response_text_and_agent_are_rejected(self):
        with pytest.raises(ValidationError):
            SupervisorOutput.model_validate(
                {
                    "intent": "travel_advice",
                    "confidence": 0.9,
                    "arguments": {"kind": "information", "query": "x"},
                    "responseText": "old contract",
                    "agent": "information_finder",
                }
            )


class TestPlanHelpers:
    def test_plan_summary_and_lookup(self):
        plan = _make_plan()
        summary = _plan_summary(plan)
        assert summary is not None
        assert summary["destination"] == "Đà Lạt"
        assert summary["days"][0]["items"][0]["itemId"] == "place-1"
        assert _find_plan_item(plan, "place-1")[0] == 1
        assert _find_plan_item(plan, "missing") is None
        assert _has_plan_day(plan, 2) is True
        assert _has_plan_day(plan, 3) is False


class TestValidatedDecision:
    def test_information_request_is_forwarded_without_response_text(self):
        decision = _validated_decision(
            _output(
                "travel_advice",
                {"kind": "information", "query": "Việt Nam có gì đặc biệt?"},
            ),
            None,
        )
        assert decision.clarification_question is None
        assert decision.information_request == {
            "kind": "information",
            "query": "Việt Nam có gì đặc biệt?",
            "requiresFreshness": False,
        }

    def test_planning_arguments_become_intake_patch(self):
        decision = _validated_decision(
            _output(
                "create_plan",
                {"kind": "planning", "destination": "Hà Nội", "days": 4},
            ),
            None,
        )
        assert decision.intake_patch == {"destination": "Hà Nội", "days": 4}

    def test_clarification_becomes_service_message_and_options(self):
        decision = _validated_decision(
            _output(
                "clarify",
                {
                    "kind": "clarification",
                    "question": "Bạn muốn chọn gì?",
                    "options": [{"label": "A", "value": "a"}],
                },
            ),
            None,
        )
        assert decision.clarification_question == "Bạn muốn chọn gì?"
        assert decision.clarification_options == ({"label": "A", "value": "a"},)

    def test_add_place_must_target_existing_day(self):
        with pytest.raises(ConversationSupervisorError, match="outside the current plan"):
            _validated_decision(
                _output(
                    "add_place",
                    {
                        "kind": "mutation",
                        "operation": {"type": "add_place", "day": 3, "name": "Cafe"},
                    },
                ),
                _make_plan(),
            )

    def test_item_operation_must_target_current_plan_item(self):
        with pytest.raises(ConversationSupervisorError, match="outside the current plan"):
            _validated_decision(
                _output(
                    "remove_place",
                    {
                        "kind": "mutation",
                        "operation": {"type": "remove_place", "itemId": "missing", "day": 1},
                    },
                ),
                _make_plan(),
            )

    def test_low_confidence_mutation_is_rejected(self):
        with pytest.raises(ConversationSupervisorError, match="confidence"):
            _validated_decision(
                _output(
                    "remove_place",
                    {
                        "kind": "mutation",
                        "operation": {"type": "remove_place", "itemId": "place-1", "day": 1},
                    },
                    confidence=0.7,
                ),
                _make_plan(),
            )

    def test_locked_item_requires_confirmation(self):
        decision = _validated_decision(
            _output(
                "remove_place",
                {
                    "kind": "mutation",
                    "operation": {"type": "remove_place", "itemId": "place-1", "day": 1},
                },
            ),
            _make_plan(locked=True),
        )
        assert decision.requires_confirmation is True

    def test_regenerate_existing_plan_requires_confirmation(self):
        decision = _validated_decision(
            _output("regenerate_plan", {"kind": "planning"}),
            _make_plan(),
        )
        assert decision.requires_confirmation is True


class TestSupervisorDecide:
    async def test_every_turn_calls_classifier(self):
        llm = FakeLLM(
            {
                "intent": "travel_advice",
                "confidence": 0.99,
                "arguments": {
                    "kind": "information",
                    "query": "Việt Nam có gì đặc biệt?",
                },
            }
        )
        decision = await ConstrainedConversationSupervisor(llm).decide(
            "tui muốn bạn kể tui nghe Việt Nam có gì đặc biệt",
            None,
            conversation_context={"currentTripIntent": {"destination": "unspecified"}},
        )
        assert decision.intent == "travel_advice"
        assert llm.calls == 1
        assert llm.last_payload["conversationContext"]["currentTripIntent"]["destination"] == "unspecified"

    async def test_schema_sent_to_llm_has_no_agent_or_response_text(self):
        llm = FakeLLM(
            {
                "intent": "create_plan",
                "confidence": 0.99,
                "arguments": {"kind": "planning", "destination": "Hà Nội", "days": 2},
            }
        )
        await ConstrainedConversationSupervisor(llm).decide("Hà Nội 2 ngày", None)
        assert set(llm.last_schema["properties"]) == {"intent", "confidence", "arguments"}

    async def test_invalid_output_is_repaired(self):
        llm = FakeLLM(
            {"intent": "travel_advice", "confidence": 0.9},
            {
                "intent": "travel_advice",
                "confidence": 0.9,
                "arguments": {"kind": "information", "query": "Huế có gì hay?"},
            },
        )
        decision = await ConstrainedConversationSupervisor(llm).decide("Huế có gì hay?", None)
        assert decision.intent == "travel_advice"
        assert llm.calls == 2

    async def test_provider_failure_is_wrapped(self):
        with pytest.raises(ConversationSupervisorError, match="could not produce"):
            await ConstrainedConversationSupervisor(FakeLLM()).decide("hi", None)

    async def test_disabled_supervisor_does_not_call_llm(self, monkeypatch):
        monkeypatch.setattr(settings, "conversation_supervisor_llm_enabled", False)
        llm = FakeLLM()
        with pytest.raises(ConversationSupervisorError, match="disabled"):
            await ConstrainedConversationSupervisor(llm).decide("hi", None)
        assert llm.calls == 0
