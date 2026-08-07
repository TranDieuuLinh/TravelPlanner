from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.plans.conversation_agents import (
    ConversationAgentContext,
    ConversationAgentDispatcher,
    agent_for_conversation_intent,
)
from app.modules.plans.conversation_supervisor import (
    ConversationDecision,
    _validated_decision,
    SupervisorOutput,
)


def _decision(intent: str) -> ConversationDecision:
    return ConversationDecision(
        intent=intent,  # type: ignore[arg-type]
        confidence=1.0,
        operation=(
            {"type": "add_place", "day": 1, "name": "Cafe"}
            if intent == "add_place"
            else None
        ),
        requires_confirmation=False,
        clarification_question=None,
        clarification_options=(),
    )


def test_allowlist_has_no_agent_for_service_owned_intents() -> None:
    assert agent_for_conversation_intent("ask_place") == "information_finder"
    assert agent_for_conversation_intent("ask_travel_information") == "information_finder"
    assert agent_for_conversation_intent("add_place") == "plan_editor"
    assert agent_for_conversation_intent("create_plan") == "explorer"
    assert agent_for_conversation_intent("regenerate_plan") == "main_planner"
    assert agent_for_conversation_intent("clarify") is None
    assert agent_for_conversation_intent("validate_plan") is None
    assert agent_for_conversation_intent("undo") is None
    assert agent_for_conversation_intent("unsupported") is None


@pytest.mark.parametrize(
    ("intent", "agent"),
    [
        ("ask_place", "information_finder"),
        ("ask_travel_information", "information_finder"),
        ("explain_plan", "information_finder"),
        ("add_place", "plan_editor"),
        ("update_place", "plan_editor"),
        ("remove_place", "plan_editor"),
        ("move_place", "plan_editor"),
        ("lock_item", "plan_editor"),
        ("unlock_item", "plan_editor"),
    ],
)
def test_information_finder_and_plan_editor_routes_are_server_allowlisted(intent, agent):
    assert agent_for_conversation_intent(intent) == agent


def test_ask_place_dispatches_read_only_information_finder() -> None:
    calls: list[str] = []

    async def finder(context: ConversationAgentContext) -> str:
        calls.append(context.decision.intent)
        return "found"

    dispatcher = ConversationAgentDispatcher({"information_finder": finder})
    result = asyncio.run(
        dispatcher.dispatch_for_decision(
            ConversationAgentContext(
                chat=None,
                turn=None,
                decision=_decision("ask_place"),
                plan=None,
            )
        )
    )
    assert result == "found"
    assert calls == ["ask_place"]


def test_edit_request_dispatches_plan_editor() -> None:
    calls: list[str] = []

    async def editor(context: ConversationAgentContext) -> str:
        calls.append(context.decision.intent)
        return "edited"

    dispatcher = ConversationAgentDispatcher({"plan_editor": editor})
    result = asyncio.run(
        dispatcher.dispatch_for_decision(
            ConversationAgentContext(
                chat=None,
                turn=None,
                decision=_decision("add_place"),
                plan=SimpleNamespace(),
            )
        )
    )
    assert result == "edited"
    assert calls == ["add_place"]


@pytest.mark.parametrize(
    ("intent", "expected_agent"),
    [
        ("create_plan", "explorer"),
        ("regenerate_plan", "main_planner"),
    ],
)
def test_planning_request_dispatches_exactly_one_agent(intent, expected_agent) -> None:
    calls: list[str] = []

    async def explorer(context: ConversationAgentContext) -> str:
        calls.append("explorer")
        return "explored"

    async def main_planner(context: ConversationAgentContext) -> str:
        calls.append("main_planner")
        return "planned"

    dispatcher = ConversationAgentDispatcher(
        {"explorer": explorer, "main_planner": main_planner}
    )
    result = asyncio.run(
        dispatcher.dispatch_for_decision(
            ConversationAgentContext(
                chat=None,
                turn=None,
                decision=_decision(intent),
                plan=None,
            )
        )
    )

    assert calls == [expected_agent]
    assert result == ("explored" if expected_agent == "explorer" else "planned")


def test_unsupported_intent_has_no_agent_or_operation() -> None:
    decision = _validated_decision(
        SupervisorOutput.model_validate(
            {
                "intent": "unsupported",
                "confidence": 0.99,
                "arguments": {
                    "kind": "command",
                    "reason": "Backup trong chat hiện chưa được hỗ trợ.",
                },
            }
        ),
        None,
    )
    assert decision.intent == "unsupported"
    assert decision.operation is None


def test_supervisor_rejects_arguments_that_do_not_match_intent() -> None:
    with pytest.raises(ValidationError, match="requires 'information' arguments"):
        SupervisorOutput.model_validate(
            {
                "intent": "ask_place",
                "confidence": 0.95,
                "arguments": {"kind": "command"},
            }
        )


def test_supervisor_forwards_validated_intake_patch() -> None:
    output = SupervisorOutput.model_validate(
        {
            "intent": "create_plan",
            "confidence": 0.98,
            "arguments": {
                "kind": "planning",
                "destination": "Hà Nội",
                "days": 4,
            },
        }
    )

    decision = _validated_decision(output, None)

    assert decision.intake_patch == {"destination": "Hà Nội", "days": 4}


def test_supervisor_rejects_planning_arguments_for_advice() -> None:
    with pytest.raises(ValidationError, match="requires 'information' arguments"):
        SupervisorOutput.model_validate(
            {
                "intent": "travel_advice",
                "confidence": 0.98,
                "arguments": {"kind": "planning", "days": 4},
            }
        )


async def _async_result(value: str) -> str:
    return value
