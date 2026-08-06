"""Tests for the conversation supervisor decision logic.

Pure, deterministic tests covering:
- SupervisorOutput schema validation (alias, extra, bounds)
- _validated_decision invariants (item/day checks, confidence, locks)
- ConstrainedConversationSupervisor.decide (LLM mocked, repair loop)
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.modules.plans.conversation_supervisor import (
    ConstrainedConversationSupervisor,
    ConversationDecision,
    ConversationSupervisorError,
    SupervisorOption,
    SupervisorOperation,
    SupervisorOutput,
    _find_plan_item,
    _has_plan_day,
    _plan_summary,
    _validated_decision,
)
from app.modules.plans.domain.entities import (
    Plan,
    PlanDay,
    PlanItem,
    PlanKind,
    PlanStatus,
    TravelIntent,
    BudgetLevel,
    TravelPace,
)


# ---------------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------------


def _make_plan(*, item_specs: list[tuple[str, bool]] | None = None) -> Plan:
    """Build a minimal Plan with 2 days and the requested items on day 1."""
    items: list[PlanItem] = []
    for idx, (item_id, locked) in enumerate(item_specs or []):
        items.append(
            PlanItem(
                itemId=item_id,
                name=f"Place {idx}",
                timeWindow="morning",
                placeType="restaurant",
                timelineCategory="food",
                locked=locked,
            )
        )
    days = [
        PlanDay(day=1, theme="Day 1", items=items),
        PlanDay(day=2, theme="Day 2", items=[]),
    ]
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
        days=days,
    )


@pytest.fixture(autouse=True)
def _enable_supervisor(monkeypatch):
    """Most tests don't care about the feature flag; enable it."""
    monkeypatch.setattr(settings, "conversation_supervisor_llm_enabled", True)


# ---------------------------------------------------------------------------
# SupervisorOutput schema
# ---------------------------------------------------------------------------


class TestSupervisorOutputSchema:
    def test_extra_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            SupervisorOutput.model_validate_json(
                json.dumps(
                    {
                        "intent": "travel_advice",
                        "confidence": 0.9,
                        "responseText": "ok",
                        "made_up_extra": "no",
                    }
                )
            )

    def test_alias_input_parses(self):
        out = SupervisorOutput.model_validate_json(
            json.dumps(
                {
                    "intent": "add_place",
                    "confidence": 0.95,
                    "responseText": "Đã thêm",
                    "operations": [{"type": "add_place", "day": 1, "name": "Cà phê"}],
                    "requiresConfirmation": True,
                }
            )
        )
        assert out.intent == "add_place"
        assert out.response_text == "Đã thêm"
        assert out.requires_confirmation is True
        assert out.operations[0].type == "add_place"

    def test_field_name_input_parses(self):
        # populate_by_name=True should also accept the snake-case name
        out = SupervisorOutput.model_validate(
            {
                "intent": "add_place",
                "confidence": 0.9,
                "response_text": "ok",
            }
        )
        assert out.response_text == "ok"
        assert out.requires_confirmation is False

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            SupervisorOutput.model_validate(
                {"intent": "travel_advice", "confidence": 1.5, "response_text": "ok"}
            )
        with pytest.raises(ValidationError):
            SupervisorOutput.model_validate(
                {"intent": "travel_advice", "confidence": -0.1, "response_text": "ok"}
            )

    def test_option_length_limits(self):
        with pytest.raises(ValidationError):
            SupervisorOption(label="x" * 121, value="ok")
        with pytest.raises(ValidationError):
            SupervisorOperation(type="add_place", day=1, itemId="x" * 129)

    def test_clarifying_question_length_limit(self):
        with pytest.raises(ValidationError):
            SupervisorOutput.model_validate(
                {
                    "intent": "clarify",
                    "confidence": 0.9,
                    "responseText": "x",
                    "clarifyingQuestion": "q" * 501,
                }
            )


# ---------------------------------------------------------------------------
# _plan_summary / _find_plan_item / _has_plan_day
# ---------------------------------------------------------------------------


class TestPlanHelpers:
    def test_none_plan_returns_none_summary(self):
        assert _plan_summary(None) is None

    def test_summary_keeps_only_items_with_ids(self):
        plan = _make_plan(item_specs=[("a", False), ("", False)])
        summary = _plan_summary(plan)
        assert summary is not None
        assert summary["id"] == "plan-1"
        assert summary["destination"] == "Đà Lạt"
        item_ids = [item["itemId"] for item in summary["days"][0]["items"]]
        assert item_ids == ["a"]

    def test_find_item_resolves_day_and_item(self):
        plan = _make_plan(item_specs=[("item-a", False)])
        result = _find_plan_item(plan, "item-a")
        assert result is not None
        day, item = result
        assert day == 1
        assert item.item_id == "item-a"

    def test_find_item_returns_none_when_missing(self):
        plan = _make_plan(item_specs=[("item-a", False)])
        assert _find_plan_item(plan, "ghost") is None
        assert _find_plan_item(None, "x") is None

    def test_has_plan_day(self):
        plan = _make_plan()
        assert _has_plan_day(plan, 1) is True
        assert _has_plan_day(plan, 2) is True
        assert _has_plan_day(plan, 3) is False
        assert _has_plan_day(None, 1) is False
        assert _has_plan_day(plan, None) is False


# ---------------------------------------------------------------------------
# _validated_decision invariants
# ---------------------------------------------------------------------------


def _out(**overrides: Any) -> SupervisorOutput:
    """Build a SupervisorOutput from kwargs (snake-case fields)."""
    base: dict[str, Any] = {
        "intent": "add_place",
        "confidence": 0.95,
        "response_text": "ok",
    }
    base.update(overrides)
    return SupervisorOutput.model_validate(base)


class TestValidatedDecision:
    def test_clarify_without_question_raises(self):
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(intent="clarify"), None,
            )

    def test_mutation_requires_exactly_one_matching_op(self):
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(_out(intent="add_place"), None)

    def test_non_mutation_with_operations_raises(self):
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="travel_advice",
                    operations=[{"type": "add_place", "day": 1, "name": "x"}],
                ),
                None,
            )

    def test_update_place_inherits_day_from_plan(self):
        # update_place needs item_id, so the supervisor day can be wrong
        # and the service overwrites it from the plan.
        plan = _make_plan(item_specs=[("p1", False)])
        out = _out(
            intent="update_place",
            operations=[{
                "type": "update_place", "itemId": "p1", "day": 2, "name": "X",
            }],
        )
        decision = _validated_decision(out, plan)
        assert decision.operation is not None
        assert decision.operation["itemId"] == "p1"
        assert decision.operation["day"] == 1

    def test_add_place_missing_day_raises(self):
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="add_place",
                    operations=[{"type": "add_place", "name": "X"}],
                ),
                None,
            )

    def test_add_place_missing_name_raises(self):
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="add_place",
                    operations=[{"type": "add_place", "day": 1}],
                ),
                None,
            )

    def test_add_place_invalid_day_raises(self):
        # day=99 is invalid per the schema (le=30), so it never reaches
        # the cross-check against the plan. Use day=3 instead, which is
        # within bounds but outside the current 2-day plan.
        plan = _make_plan()
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="add_place",
                    operations=[{"type": "add_place", "day": 3, "name": "X"}],
                ),
                plan,
            )

    def test_move_place_requires_to_day(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="move_place",
                    operations=[{"type": "move_place", "itemId": "p1", "day": 1}],
                ),
                plan,
            )

    def test_move_place_invalid_to_day_raises(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="move_place",
                    operations=[{
                        "type": "move_place", "itemId": "p1", "day": 1, "toDay": 3,
                    }],
                ),
                plan,
            )

    def test_update_place_requires_name(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="update_place",
                    operations=[{
                        "type": "update_place", "itemId": "p1", "day": 1,
                    }],
                ),
                plan,
            )

    def test_remove_requires_item_id_and_day(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="remove_place",
                    operations=[{"type": "remove_place", "day": 1}],
                ),
                plan,
            )

    def test_lock_requires_item_id_and_day(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="lock_item",
                    operations=[{"type": "lock_item", "day": 1}],
                ),
                plan,
            )

    def test_unknown_item_id_raises(self):
        plan = _make_plan()
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="remove_place",
                    operations=[{
                        "type": "remove_place", "itemId": "ghost", "day": 1,
                    }],
                ),
                plan,
            )

    def test_low_confidence_mutation_rejected(self):
        plan = _make_plan(item_specs=[("p1", False)])
        with pytest.raises(ConversationSupervisorError):
            _validated_decision(
                _out(
                    intent="remove_place",
                    confidence=0.5,
                    operations=[{
                        "type": "remove_place", "itemId": "p1", "day": 1,
                    }],
                ),
                plan,
            )

    def test_locked_item_requires_confirmation(self):
        plan = _make_plan(item_specs=[("p1", True)])
        decision = _validated_decision(
            _out(
                intent="remove_place",
                operations=[{
                    "type": "remove_place", "itemId": "p1", "day": 1,
                }],
            ),
            plan,
        )
        assert decision.requires_confirmation is True

    def test_unlock_does_not_require_confirmation(self):
        plan = _make_plan(item_specs=[("p1", True)])
        decision = _validated_decision(
            _out(
                intent="unlock_item",
                operations=[{
                    "type": "unlock_item", "itemId": "p1", "day": 1,
                }],
            ),
            plan,
        )
        assert decision.requires_confirmation is False

    def test_regenerate_plan_with_existing_plan_requires_confirmation(self):
        plan = _make_plan()
        decision = _validated_decision(
            _out(intent="regenerate_plan", requires_confirmation=True),
            plan,
        )
        assert decision.requires_confirmation is True

    def test_options_passthrough(self):
        decision = _validated_decision(
            SupervisorOutput.model_validate(
                {
                    "intent": "clarify",
                    "confidence": 0.9,
                    "responseText": "x",
                    "clarifyingQuestion": "Bạn muốn làm gì?",
                    "options": [{"label": "L1", "value": "v1"}],
                }
            ),
            None,
        )
        assert decision.options == ({"label": "L1", "value": "v1"},)

    def test_message_prefers_clarification_question(self):
        decision = _validated_decision(
            SupervisorOutput.model_validate(
                {
                    "intent": "clarify",
                    "confidence": 0.9,
                    "responseText": "long response",
                    "clarifyingQuestion": "short clarifier",
                }
            ),
            None,
        )
        assert decision.message == "short clarifier"


# ---------------------------------------------------------------------------
# ConstrainedConversationSupervisor.decide (LLM mocked)
# ---------------------------------------------------------------------------


class _FakeLLM:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls = 0
        self.last_schema = None

    async def generate_structured_json(self, system_prompt, user_payload, *, response_schema):
        self.calls += 1
        self.last_schema = response_schema
        if not self.outputs:
            raise RuntimeError("exhausted")
        return self.outputs.pop(0)


class TestSupervisorDecide:
    async def test_high_signal_capability_question_does_not_call_llm(self):
        llm = _FakeLLM([])
        supervisor = ConstrainedConversationSupervisor(llm=llm)

        decision = await supervisor.decide("bạn code được không?", None)

        assert decision.intent == "travel_advice"
        assert "code" in (decision.message or "")
        assert llm.calls == 0

    async def test_clear_plan_request_enters_intake_instead_of_repeated_clarify(self):
        llm = _FakeLLM([])
        supervisor = ConstrainedConversationSupervisor(llm=llm)

        decision = await supervisor.decide(
            "lên kế hoạch du lịch 2 ngày giúp tôi",
            None,
        )

        assert decision.intent == "create_plan"
        assert decision.confidence == 1.0
        assert llm.calls == 0

    async def test_follow_up_place_requirement_enters_existing_intake(self):
        llm = _FakeLLM([])
        supervisor = ConstrainedConversationSupervisor(llm=llm)

        decision = await supervisor.decide(
            "tôi muốn ít nhất phải thăm làng Bắc",
            None,
            conversation_context={
                "currentTripIntent": {
                    "destination": "unspecified",
                    "timing": {"days": 2},
                }
            },
        )

        assert decision.intent == "create_plan"
        assert llm.calls == 0

    async def test_disabled_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "conversation_supervisor_llm_enabled", False)
        supervisor = ConstrainedConversationSupervisor(llm=_FakeLLM([]))
        with pytest.raises(ConversationSupervisorError):
            await supervisor.decide("hi", None)

    async def test_happy_path_returns_decision(self):
        llm = _FakeLLM([
            json.dumps({
                "intent": "add_place",
                "confidence": 0.92,
                "responseText": "ok",
                "operations": [{"type": "add_place", "day": 1, "name": "X"}],
            })
        ])
        supervisor = ConstrainedConversationSupervisor(llm=llm)
        plan = _make_plan()
        decision = await supervisor.decide("add X to day 1", plan)
        assert isinstance(decision, ConversationDecision)
        assert decision.intent == "add_place"
        assert decision.confidence == 0.92
        assert decision.operation is not None
        assert llm.calls == 1
        # the JSON schema sent to the LLM must be the alias form
        assert "responseText" in llm.last_schema["properties"]

    async def test_first_invalid_repaired_by_secondary_call(self):
        llm = _FakeLLM([
            "{not-json",
            json.dumps({
                "intent": "add_place",
                "confidence": 0.92,
                "responseText": "ok",
                "operations": [{"type": "add_place", "day": 1, "name": "X"}],
            }),
        ])
        supervisor = ConstrainedConversationSupervisor(llm=llm)
        plan = _make_plan()
        decision = await supervisor.decide("add X", plan)
        assert decision.intent == "add_place"
        assert llm.calls == 2

    async def test_two_failures_raise(self):
        llm = _FakeLLM(["x", "y"])
        supervisor = ConstrainedConversationSupervisor(llm=llm)
        with pytest.raises(ConversationSupervisorError):
            await supervisor.decide("hi", None)
        assert llm.calls == 2

    async def test_llm_runtime_error_raises_supervisor_error(self):
        class _BrokenLLM:
            async def generate_structured_json(self, *args, **kwargs):
                raise RuntimeError("upstream down")

        supervisor = ConstrainedConversationSupervisor(llm=_BrokenLLM())
        with pytest.raises(ConversationSupervisorError):
            await supervisor.decide("hi", None)

    async def test_decision_includes_options_as_dicts(self):
        llm = _FakeLLM([
            json.dumps({
                "intent": "clarify",
                "confidence": 0.9,
                "responseText": "x",
                "clarifyingQuestion": "Bạn muốn?",
                "options": [
                    {"label": "Tư vấn", "value": "Tư vấn thêm"},
                ],
            })
        ])
        supervisor = ConstrainedConversationSupervisor(llm=llm)
        decision = await supervisor.decide("?", None)
        assert dict(decision.options[0]) == {
            "label": "Tư vấn", "value": "Tư vấn thêm",
        }

    async def test_repair_path_uses_repair_prompt(self):
        seen_prompts: list[str] = []

        class _RecordingLLM:
            def __init__(self):
                self.outputs = iter([
                    "garbage",
                    json.dumps({
                        "intent": "add_place",
                        "confidence": 0.9,
                        "responseText": "ok",
                        "operations": [{"type": "add_place", "day": 1, "name": "X"}],
                    }),
                ])

            async def generate_structured_json(self, system_prompt, user_payload, *, response_schema):
                seen_prompts.append(system_prompt)
                return next(self.outputs)

        supervisor = ConstrainedConversationSupervisor(llm=_RecordingLLM())
        plan = _make_plan()
        await supervisor.decide("hi", plan)
        assert "đang sửa" in seen_prompts[1].lower()
