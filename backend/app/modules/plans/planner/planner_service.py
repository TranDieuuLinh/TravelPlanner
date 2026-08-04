from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import DayBrief, MacroPlan, TravelIntent
from app.modules.plans.planner.prompt_builder import PlanPromptBuilder


class PlannerService:
    def __init__(self, llm_client: LLMClient, prompt_builder: PlanPromptBuilder | None = None) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder or PlanPromptBuilder()

    async def create_main_macro_plan(self, intent: TravelIntent) -> MacroPlan:
        await self.llm_client.generate_profile_plan(self.prompt_builder.build_main_prompt(intent))
        return self._build_macro_plan(intent, "Main")

    async def create_backup_macro_plan(self, intent: TravelIntent, reason: str) -> MacroPlan:
        await self.llm_client.generate_profile_plan(self.prompt_builder.build_backup_prompt(intent, reason))
        return self._build_macro_plan(intent, "Backup")

    def _build_macro_plan(self, intent: TravelIntent, mode: str) -> MacroPlan:
        focus = intent.interests or ["culture", "food", "local life"]
        briefs = [
            DayBrief(
                day=day,
                theme=f"{mode} day {day}: {focus[(day - 1) % len(focus)].title()}",
                targetArea=f"{intent.destination} area {day}",
                notes=[f"Pace: {intent.pace}", f"Budget: {intent.budget}"],
            )
            for day in range(1, intent.days + 1)
        ]
        return MacroPlan(title=f"{mode} plan for {intent.destination}", destination=intent.destination, dayBriefs=briefs)
