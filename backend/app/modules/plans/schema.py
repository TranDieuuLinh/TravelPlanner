from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import (
    CheckReport,
    Plan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace
from app.modules.plans.dto.agent_contracts import PlanningIntent, TripPlanningSpec


class FeatureMapItem(BaseModel):
    stage: str
    feature: str
    description: str


class ExplorerRequest(BaseModel):
    destination: str
    days: Annotated[int, Field(ge=1, le=30)] = 3
    budget: BudgetLevel = BudgetLevel.medium
    travel_style: Annotated[str, Field(alias="travelStyle")] = "local"
    pace: TravelPace = TravelPace.balanced
    interests: list[str] = Field(default_factory=list)
    must_visit_places: Annotated[list[str], Field(alias="mustVisitPlaces")] = Field(default_factory=list)
    avoid_places: Annotated[list[str], Field(alias="avoidPlaces")] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class SelectedPlaceCreate(BaseModel):
    name: str
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    priority: Annotated[int, Field(default=1, ge=1, le=5)]
    must_visit: Annotated[bool, Field(default=False, alias="mustVisit")]
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    tags: list[str] = Field(default_factory=list)
    source_refs: Annotated[list[str], Field(alias="sourceRefs")] = Field(
        default_factory=list
    )
    notes: str | None = None

    model_config = {"populate_by_name": True}


class MainPlanCreate(ExplorerRequest):
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    selected_places: Annotated[
        list[SelectedPlaceCreate | str],
        Field(alias="selectedPlaces"),
    ] = Field(default_factory=list)
    user_status: Annotated[UserStatus, Field(alias="userStatus")] = Field(
        default_factory=UserStatus
    )


class MainPlanFromExplorerCreate(BaseModel):
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    selected_places: Annotated[
        list[SelectedPlaceCreate],
        Field(alias="selectedPlaces"),
    ] = Field(default_factory=list)
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
class PlanningContextCreate(BaseModel):
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    selected_places: Annotated[
        list[SelectedPlaceCreate | str],
        Field(alias="selectedPlaces"),
    ] = Field(default_factory=list)
    user_status: Annotated[UserStatus, Field(alias="userStatus")] = Field(
        default_factory=UserStatus
    )

    model_config = {"populate_by_name": True}


class BackupPlanCreate(BaseModel):
    reason: str = "overall_check_risk"
    constraints: list[str] = Field(default_factory=list)
    keep_days: Annotated[bool, Field(alias="keepDays")] = True
    avoid_outdoor: Annotated[bool, Field(alias="avoidOutdoor")] = False


TravelIntentRead = TravelIntent
PlanRead = Plan
CheckReportRead = CheckReport


class PlanBundleRead(BaseModel):
    main_plan: Annotated[PlanRead, Field(alias="mainPlan")]
    backup_plan: Annotated[PlanRead, Field(alias="backupPlan")]
    validation: CheckReportRead

    model_config = {"populate_by_name": True}
