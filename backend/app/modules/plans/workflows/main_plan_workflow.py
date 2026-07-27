from uuid import uuid4

from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import Plan
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.schema import MainPlanCreate


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        planner: PlannerService,
        finder: FinderService,
        checker: OverallChecker,
    ) -> None:
        self.explorer = explorer
        self.planner = planner
        self.finder = finder
        self.checker = checker

    async def run(self, payload: MainPlanCreate) -> Plan:
        intent = self.explorer.explore(payload)
        macro_plan = await self.planner.create_main_macro_plan(intent)
        days = self.finder.fill_main_plan(macro_plan, intent, payload.selected_places)
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.checking,
            title=macro_plan.title,
            destination=intent.destination,
            intent=intent,
            macroPlan=macro_plan,
            days=days,
        )
        check_report = self.checker.check(plan)
        return plan.model_copy(update={"status": PlanStatus.locked, "check_report": check_report})
