from typing import Protocol

from app.modules.plan_editor.contract import NaturalLanguagePlanEdit, PlanEditContext


class PlanEditIntentResolver(Protocol):
    async def resolve(self, payload: PlanEditContext) -> NaturalLanguagePlanEdit:
        """Interpret one message against a compact, user-editable plan view."""
