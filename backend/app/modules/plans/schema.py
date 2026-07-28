from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import CheckReport, Plan, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace


class FeatureMapItem(BaseModel):
    stage: str
    feature: str
    description: str


class ExplorerRequest(BaseModel):
    destination: str
    days: Annotated[int, Field(ge=1, le=30)] = 3
    budget: BudgetLevel = BudgetLevel.balanced
    travel_style: Annotated[str, Field(alias="travelStyle")] = "local"
    pace: TravelPace = TravelPace.balanced
    interests: list[str] = Field(default_factory=list)
    must_visit_places: Annotated[list[str], Field(alias="mustVisitPlaces")] = Field(default_factory=list)
    avoid_places: Annotated[list[str], Field(alias="avoidPlaces")] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class MainPlanCreate(ExplorerRequest):
    selected_places: Annotated[list[str], Field(alias="selectedPlaces")] = Field(default_factory=list)


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
