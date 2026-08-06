from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from app.modules.plans.information_finder.schema import InformationQuery


ConversationAgentName = Literal[
    "explorer",
    "information_finder",
    "main_planner",
    "plan_editor",
]


def agent_for_conversation_intent(
    intent: str,
) -> ConversationAgentName | None:
    """Return the allowlisted conversation agent for an intent."""
    if intent in {"ask_place", "ask_travel_information", "travel_advice", "explain_plan"}:
        return "information_finder"
    if intent in {"create_plan", "regenerate_plan"}:
        return "main_planner"
    if intent in {
        "add_place", "update_place", "remove_place", "move_place",
        "lock_item", "unlock_item",
    }:
        return "plan_editor"
    return None


@dataclass
class ConversationAgentContext:
    """Request envelope passed between the supervisor and a conversation agent."""

    chat: Any
    turn: Any
    decision: Any
    plan: Any
    images: list[Any] = field(default_factory=list)
    confirmed: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    information_query: InformationQuery | None = None


class ConversationAgent(Protocol):
    name: ConversationAgentName

    async def run(self, context: ConversationAgentContext) -> Any: ...


AgentHandler = Callable[[ConversationAgentContext], Awaitable[Any]]


@dataclass
class _CallbackAgent:
    name: ConversationAgentName
    handler: AgentHandler

    async def run(self, context: ConversationAgentContext) -> Any:
        return await self.handler(context)


class ExplorerAgent(_CallbackAgent):
    def __init__(self, handler: AgentHandler) -> None:
        super().__init__("explorer", handler)


class InformationFinderAgent(_CallbackAgent):
    def __init__(self, handler: AgentHandler) -> None:
        super().__init__("information_finder", handler)


class MainPlanningAgent(_CallbackAgent):
    def __init__(self, handler: AgentHandler) -> None:
        super().__init__("main_planner", handler)


class PlanEditorAgent(_CallbackAgent):
    def __init__(self, handler: AgentHandler) -> None:
        super().__init__("plan_editor", handler)


class ConversationAgentDispatcher:
    """Allowlisted dispatcher between supervisor decisions and domain agents."""

    def __init__(self, handlers: dict[ConversationAgentName, AgentHandler]) -> None:
        agent_types: dict[ConversationAgentName, type[_CallbackAgent]] = {
            "explorer": ExplorerAgent,
            "information_finder": InformationFinderAgent,
            "main_planner": MainPlanningAgent,
            "plan_editor": PlanEditorAgent,
        }
        self._agents: dict[ConversationAgentName, ConversationAgent] = {
            name: agent_types[name](handler)
            for name, handler in handlers.items()
        }

    async def dispatch(
        self,
        agent: ConversationAgentName,
        context: ConversationAgentContext,
    ) -> Any:
        selected = self._agents.get(agent)
        if selected is None:
            raise ValueError(f"Unknown conversation agent: {agent}")
        return await selected.run(context)

    async def dispatch_for_decision(
        self,
        context: ConversationAgentContext,
    ) -> Any:
        expected = agent_for_conversation_intent(context.decision.intent)
        if expected is None:
            raise ValueError(
                f"Intent {context.decision.intent!r} does not route to an agent"
            )
        # Legacy callers did not carry an agent field. They still route via
        # this server-owned mapping; an explicitly supplied wrong agent is
        # rejected.
        if context.decision.agent is not None and context.decision.agent != expected:
            raise ValueError(
                f"Agent {context.decision.agent!r} does not match intent "
                f"{context.decision.intent!r}"
            )
        return await self.dispatch(expected, context)
