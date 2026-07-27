from fastapi import HTTPException, status

from app.modules.plans.domain.entities import Plan


class PlanRepository:
    _plans: dict[str, Plan] = {}

    def save(self, plan: Plan) -> Plan:
        self._plans[plan.id] = plan
        return plan

    def get(self, plan_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        return plan
