from app.modules.plans.domain.entities import Plan, TravelIntent
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.repository import PlanRepository
from app.modules.plans.schema import BackupPlanCreate, ExplorerRequest, FeatureMapItem, MainPlanCreate, PlanBundleRead
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow


class PlanService:
    def __init__(
        self,
        repository: PlanRepository,
        explorer: ExplorerService,
        main_workflow: MainPlanWorkflow,
        backup_workflow: BackupPlanWorkflow,
    ) -> None:
        self.repository = repository
        self.explorer = explorer
        self.main_workflow = main_workflow
        self.backup_workflow = backup_workflow

    def feature_map(self) -> list[FeatureMapItem]:
        return [
            FeatureMapItem(stage="explore", feature="Explorer", description="Clarify destination, budget, pace, interests, and constraints."),
            FeatureMapItem(stage="create", feature="Planner", description="Generate MacroPlan and DayBriefs for the main itinerary."),
            FeatureMapItem(stage="fill", feature="Finder", description="Choose day windows, fill places, and commit each day."),
            FeatureMapItem(stage="check", feature="CheckOverall", description="Review weather, transport, availability, and plan risks."),
            FeatureMapItem(stage="backup", feature="Backup Planner", description="Create a separate backup plan without mutating the locked main plan."),
        ]

    def explore(self, payload: ExplorerRequest) -> TravelIntent:
        return self.explorer.explore(payload)

    async def create_main_plan(self, payload: MainPlanCreate) -> Plan:
        plan = await self.main_workflow.run(payload)
        self.repository.save(plan)
        return plan

    async def create_backup_plan(self, plan_id: str, payload: BackupPlanCreate) -> PlanBundleRead:
        main_plan = self.repository.get(plan_id)
        backup_plan, validation = await self.backup_workflow.run(main_plan, payload)
        self.repository.save(backup_plan)
        return PlanBundleRead(
            mainPlan=main_plan.model_dump(by_alias=True),
            backupPlan=backup_plan.model_dump(by_alias=True),
            validation=validation.model_dump(by_alias=True),
        )
