from uuid import uuid4

from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.domain.entities import CheckReport, Plan, UnscheduledPlace
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    FinderAgentInput,
    PlanningIntent,
    PlanningMode,
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
        selected_places = [
            SelectedPlaceContext(
                placeId=item.place_id,
                name=item.name,
                address=item.address,
                mustVisit=item.place_type == "must_visit",
                regionKey=item.region_key,
                latitude=item.latitude,
                longitude=item.longitude,
                sourceRefs=item.source_refs,
                sourceProvider=item.source_provider,
                tags=item.tags,
                notes=item.notes,
                personalNotes=item.personal_notes,
            )
            for day in main_plan.days
            for item in day.items
            if item.source == "selected_place"
        ]
        if payload.avoid_outdoor:
            selected_places = [
                place
                for place in selected_places
                if not self._selected_place_is_outdoor(place)
            ]
        backup_constraints = list(
            dict.fromkeys(
                [
                    *main_plan.intent.constraints,
                    *payload.constraints,
                    *(["avoid_outdoor"] if payload.avoid_outdoor else []),
                ]
            )
        )
        backup_intent = main_plan.intent.model_copy(
            update={"constraints": backup_constraints}
        )
        planner_output = await self.planner.create_backup_macro_plan(
            backup_intent,
            payload.reason,
            trip_spec=TripPlanningSpec(
                days=main_plan.intent.days,
                budget={"level": backup_intent.budget},
            ),
            region_key=(
                main_plan.macro_plan.region_key
                or normalize_region_key(main_plan.destination)
            ),
            selected_places=selected_places,
            original_macro_plan=main_plan.macro_plan,
            check_report=main_plan.check_report,
        )
        macro_plan = planner_output.macro_plan
        finder_output = self.finder.fill_agent_plan(
            FinderAgentInput(
                mode=PlanningMode.backup,
                intent=PlanningIntent(
                    destination=backup_intent.destination,
                    travelStyle=backup_intent.travel_style,
                    pace=backup_intent.pace,
                    interests=backup_intent.interests,
                    mustVisitPlaces=backup_intent.must_visit_places,
                    avoidPlaces=backup_intent.avoid_places,
                    constraints=backup_intent.constraints,
                    constraintPolicy=backup_intent.constraint_policy,
                    clarifyingQuestions=backup_intent.clarifying_questions,
                ),
                tripSpec=planner_output.trip_spec,
                macroPlan=macro_plan,
                selectedPlaces=selected_places,
                userStatus=main_plan.initial_user_status,
            )
        )
        unscheduled_places = [
            *finder_output.unscheduled_places,
            *[
                UnscheduledPlace(
                    placeId=item.place.place_id,
                    name=item.place.name,
                    reasonCode=item.reason_code,
                    reason=item.reason,
                )
                for item in planner_output.unallocated_selected_places
            ],
        ]
        backup_plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.backup,
            status=PlanStatus.checking,
            title=macro_plan.title,
            destination=main_plan.destination,
            parentPlanId=main_plan.id,
            intent=backup_intent,
            macroPlan=macro_plan,
            days=finder_output.final_days,
            initialUserStatus=main_plan.initial_user_status,
            finalUserStatus=finder_output.final_user_status,
            finalPlanStatus=finder_output.final_plan_status,
            unscheduledPlaces=unscheduled_places,
            planningAssumptions=planner_output.assumptions,
            warnings=[
                *planner_output.warnings,
                *finder_output.warnings,
                *(
                    [
                        "keepDays=false cannot change the backup duration "
                        "without an explicit replacement day count."
                    ]
                    if not payload.keep_days
                    else []
                ),
            ],
        )
        validation = self.validator.validate(main_plan, backup_plan)
        status = (
            PlanStatus.locked
            if validation.status == "valid"
            else PlanStatus.failed
            if validation.status == "invalid"
            else PlanStatus.draft
        )
        return backup_plan.model_copy(update={"status": status, "check_report": validation}), validation

    def _selected_place_is_outdoor(
        self,
        place: SelectedPlaceContext,
    ) -> bool:
        markers = {"outdoor", "nature", "park", "beach", "hiking"}
        if markers.intersection(tag.casefold() for tag in place.tags):
            return True
        if place.place_id:
            stored_place = self.finder.place_tool.get(place.place_id)
            if stored_place is not None:
                values = {
                    stored_place.place_type.casefold(),
                    *(tag.casefold() for tag in stored_place.tags),
                }
                return bool(values.intersection(markers))
        return False
