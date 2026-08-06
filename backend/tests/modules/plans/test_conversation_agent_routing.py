from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.modules.plans.conversation_agents import (
    ConversationAgentContext,
    ConversationAgentDispatcher,
    agent_for_conversation_intent,
)
from app.modules.plans.conversation_supervisor import (
    ConversationDecision,
    _deterministic_decision,
    _validated_decision,
    SupervisorOutput,
    ConversationSupervisorError,
)


def _decision(intent: str, agent: str | None = None) -> ConversationDecision:
    return ConversationDecision(
        intent=intent,  # type: ignore[arg-type]
        confidence=1.0,
        operation=(
            {"type": "add_place", "day": 1, "name": "Cafe"}
            if intent == "add_place"
            else None
        ),
        requires_confirmation=False,
        message="ok",
        options=(),
        agent=agent,  # type: ignore[arg-type]
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


def test_dispatcher_rejects_intent_agent_mismatch() -> None:
    dispatcher = ConversationAgentDispatcher(
        {
            "information_finder": lambda context: _async_result("finder"),
            "plan_editor": lambda context: _async_result("editor"),
        }
    )
    context = ConversationAgentContext(
        chat=None,
        turn=None,
        decision=_decision("ask_place", "plan_editor"),
        plan=None,
    )
    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(dispatcher.dispatch_for_decision(context))


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
                decision=_decision("ask_place", "information_finder"),
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
                decision=_decision("add_place", "plan_editor"),
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
                decision=_decision(intent, expected_agent),
                plan=None,
            )
        )
    )

    assert calls == [expected_agent]
    assert result == ("explored" if expected_agent == "explorer" else "planned")


def test_backup_is_deterministically_unsupported_in_chat() -> None:
    decision = _deterministic_decision("create backup", None, None)
    assert decision is not None
    assert decision.intent == "unsupported"
    assert decision.agent is None
    assert decision.operation is None


def test_supervisor_repairs_mismatched_agent_by_rejecting_it() -> None:
    output = SupervisorOutput.model_validate(
        {
            "intent": "ask_place",
            "confidence": 0.95,
            "responseText": "ok",
            "agent": "plan_editor",
        }
    )
    with pytest.raises(ConversationSupervisorError, match="does not match"):
        _validated_decision(output, None)


def test_supervisor_forwards_validated_intake_patch() -> None:
    output = SupervisorOutput.model_validate(
        {
            "intent": "create_plan",
            "confidence": 0.98,
            "responseText": "Mình sẽ lên lịch trình.",
            "agent": "explorer",
            "intakePatch": {"destination": "Hà Nội", "days": 4},
        }
    )

    decision = _validated_decision(output, None)

    assert decision.intake_patch == {"destination": "Hà Nội", "days": 4}


def test_supervisor_rejects_intake_patch_for_non_planning_intent() -> None:
    output = SupervisorOutput.model_validate(
        {
            "intent": "travel_advice",
            "confidence": 0.98,
            "responseText": "Thông tin tham khảo.",
            "agent": "information_finder",
            "intakePatch": {"days": 4},
        }
    )

    with pytest.raises(ConversationSupervisorError, match="non-planning"):
        _validated_decision(output, None)


async def _async_result(value: str) -> str:
    return value
