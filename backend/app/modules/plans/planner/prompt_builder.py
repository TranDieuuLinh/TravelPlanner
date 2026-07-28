from app.modules.plans.domain.entities import TravelIntent


class PlanPromptBuilder:
    def build_main_prompt(self, intent: TravelIntent) -> str:
        interests = ", ".join(intent.interests) or "general highlights"
        return f"Create a {intent.days}-day {intent.budget} trip to {intent.destination} for {interests}."

    def build_backup_prompt(self, intent: TravelIntent, reason: str) -> str:
        return f"Create a backup trip for {intent.destination}. Reason: {reason}."
