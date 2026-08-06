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
    assert agent_for_conversation_intent("clarify") is None
    assert agent_for_conversation_intent("validate_plan") is None
    assert agent_for_conversation_intent("undo") is None
    assert agent_for_conversation_intent("unsupported") is None


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


async def _async_result(value: str) -> str:
    return value
