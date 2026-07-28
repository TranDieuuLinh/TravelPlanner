from uuid import uuid4

from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.domain.entities import CheckReport, Plan
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.schema import BackupPlanCreate


class BackupPlanWorkflow:
    def __init__(
        self,
        planner: PlannerService,
        finder: FinderService,
        validator: BackupValidator,
    ) -> None:
        self.planner = planner
        self.finder = finder
        self.validator = validator

    async def run(self, main_plan: Plan, payload: BackupPlanCreate) -> tuple[Plan, CheckReport]:
        selected_places = [item.name for day in main_plan.days for item in day.items if item.place_type == "must_visit"]
        if payload.avoid_outdoor:
            selected_places = [place for place in selected_places if "park" not in place.lower()]
        selected_place_contexts = [
            SelectedPlaceContext(name=place, mustVisit=True)
            for place in selected_places
        ]
        planner_output = await self.planner.create_backup_macro_plan(
            main_plan.intent,
            payload.reason,
            trip_spec=TripPlanningSpec(days=main_plan.intent.days),
            region_key=(
                main_plan.macro_plan.region_key
                or normalize_region_key(main_plan.destination)
            ),
            selected_places=selected_place_contexts,
            original_macro_plan=main_plan.macro_plan,
            check_report=main_plan.check_report,
        )
        macro_plan = planner_output.macro_plan
        finder_result = self.finder.fill_backup_plan(
            macro_plan,
            main_plan.intent,
            selected_place_contexts,
            user_status=main_plan.initial_user_status,
        )
        backup_plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.backup,
            status=PlanStatus.checking,
            title=macro_plan.title,
            destination=main_plan.destination,
            parentPlanId=main_plan.id,
            intent=main_plan.intent,
            macroPlan=macro_plan,
            days=finder_result.days,
            initialUserStatus=main_plan.initial_user_status,
            finalUserStatus=finder_result.final_user_status,
            finalPlanStatus=finder_result.final_plan_status,
            unscheduledPlaces=finder_result.unscheduled_places,
        )
        validation = self.validator.validate(main_plan, backup_plan)
        status = PlanStatus.locked if validation.status == "valid" else PlanStatus.failed
        return backup_plan.model_copy(update={"status": status, "check_report": validation}), validation
