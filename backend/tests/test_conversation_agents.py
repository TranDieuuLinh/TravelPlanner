from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.modules.plans.conversation_agents import (
    ConversationAgentContext,
    ConversationAgentDispatcher,
    agent_for_conversation_intent,
)
from app.modules.plans.conversation_supervisor import (
    ConversationDecision,
    SupervisorOutput,
)


def test_dispatcher_calls_only_registered_agent() -> None:
    calls: list[str] = []

    async def run_editor(context: ConversationAgentContext) -> str:
        calls.append(context.decision.intent)
        return "edited"

    dispatcher = ConversationAgentDispatcher({"plan_editor": run_editor})
    decision = ConversationDecision(
        intent="add_place",
        confidence=1.0,
        operation={"type": "add_place", "day": 1, "name": "Cafe"},
        requires_confirmation=False,
        clarification_question=None,
        clarification_options=(),
    )

    result = asyncio.run(
        dispatcher.dispatch(
            "plan_editor",
            ConversationAgentContext(
                chat=None,
                turn=None,
                decision=decision,
                plan=None,
            ),
        )
    )

    assert result == "edited"
    assert calls == ["add_place"]


def test_intents_map_to_the_temporary_agent_set() -> None:
    assert agent_for_conversation_intent("create_plan") == "explorer"
    assert agent_for_conversation_intent("regenerate_plan") == "main_planner"
    assert agent_for_conversation_intent("travel_advice") == "information_finder"
    assert agent_for_conversation_intent("ask_place") == "information_finder"
    assert agent_for_conversation_intent("ask_travel_information") == "information_finder"
    assert agent_for_conversation_intent("explain_plan") == "information_finder"
    assert agent_for_conversation_intent("add_place") == "plan_editor"
    assert agent_for_conversation_intent("validate_plan") is None
    assert agent_for_conversation_intent("create_backup") is None


def test_supervisor_output_rejects_agent_field() -> None:
    with pytest.raises(ValidationError):
        SupervisorOutput.model_validate(
            {
                "intent": "create_plan",
                "confidence": 1.0,
                "arguments": {"kind": "planning", "destination": "Hà Nội"},
                "agent": "explorer",
            }
        )
