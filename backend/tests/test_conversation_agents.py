from __future__ import annotations

import asyncio

from app.modules.plans.conversation_agents import (
    ConversationAgentContext,
    ConversationAgentDispatcher,
)
from app.modules.plans.conversation_supervisor import (
    ConversationDecision,
    SupervisorOutput,
    _agent_for_intent,
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
        message=None,
        options=(),
        agent="plan_editor",
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
    assert _agent_for_intent("create_plan") == "explorer"
    assert _agent_for_intent("regenerate_plan") == "main_planner"
    assert _agent_for_intent("travel_advice") == "information_finder"
    assert _agent_for_intent("ask_place") == "information_finder"
    assert _agent_for_intent("ask_travel_information") == "information_finder"
    assert _agent_for_intent("explain_plan") == "information_finder"
    assert _agent_for_intent("add_place") == "plan_editor"
    assert _agent_for_intent("validate_plan") is None
    assert _agent_for_intent("create_backup") is None


def test_supervisor_output_accepts_optional_agent() -> None:
    output = SupervisorOutput.model_validate(
        {
            "intent": "create_plan",
            "confidence": 1.0,
            "responseText": "Đang chuẩn bị lịch trình.",
            "agent": "explorer",
        }
    )

    assert output.agent == "explorer"
