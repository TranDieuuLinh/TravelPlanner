import json

from app.modules.plans.dto.agent_contracts import PlannerAgentInput

class PlanPromptBuilder:
    def build_prompt(self, planner_input: PlannerAgentInput) -> str:
        payload = planner_input.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
        return (
            "Create only a MacroPlan and DayBriefs. Do not invent exact opening "
            "hours, prices, routes, or detailed itinerary times. Allocate every "
            "confirmed selected place to a day or report it as unallocated. "
            "Use the supplied immutable region statistics snapshot.\n"
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )
