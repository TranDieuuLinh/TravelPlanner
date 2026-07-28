from pydantic import BaseModel, Field

from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace


class TravelIntent(BaseModel):
    destination: str
    days: int
    budget: BudgetLevel
    travel_style: str = Field(alias="travelStyle")
    pace: TravelPace
    interests: list[str] = Field(default_factory=list)
    must_visit_places: list[str] = Field(default_factory=list, alias="mustVisitPlaces")
    avoid_places: list[str] = Field(default_factory=list, alias="avoidPlaces")
    constraints: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list, alias="clarifyingQuestions")

    model_config = {"populate_by_name": True}


class DayPartGoals(BaseModel):
    morning: str | None = None
    lunch: str | None = None
    afternoon: str | None = None
    evening: str | None = None


class RegionSnapshotReference(BaseModel):
    region_key: str = Field(alias="regionKey")
    snapshot_id: str = Field(alias="snapshotId")
    catalog_version: int = Field(alias="catalogVersion")
    algorithm_version: str = Field(alias="algorithmVersion")
    generated_at: str = Field(alias="generatedAt")

    model_config = {"populate_by_name": True}


class DayBrief(BaseModel):
    day: int
    theme: str
    target_area: str = Field(alias="targetArea")
    target_region_key: str | None = Field(default=None, alias="targetRegionKey")
    focus_tags: list[str] = Field(default_factory=list, alias="focusTags")
    pace: TravelPace = TravelPace.balanced
    day_part_goals: DayPartGoals = Field(
        default_factory=DayPartGoals,
        alias="dayPartGoals",
    )
    allocated_selected_place_refs: list[str] = Field(
        default_factory=list,
        alias="allocatedSelectedPlaceRefs",
    )
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MacroPlan(BaseModel):
    title: str
    destination: str
    region_key: str | None = Field(default=None, alias="regionKey")
    snapshot_ref: RegionSnapshotReference | None = Field(
        default=None,
        alias="snapshotRef",
    )
    day_briefs: list[DayBrief] = Field(alias="dayBriefs")

    model_config = {"populate_by_name": True}


class PlanItem(BaseModel):
    name: str
    time_window: str = Field(alias="timeWindow")
    place_type: str = Field(alias="placeType")
    notes: str | None = None

    model_config = {"populate_by_name": True}


class PlanDay(BaseModel):
    day: int
    theme: str
    items: list[PlanItem]


class CheckIssue(BaseModel):
    code: str
    severity: str
    message: str


class CheckReport(BaseModel):
    status: str
    issues: list[CheckIssue] = Field(default_factory=list)
    summary: str


class Plan(BaseModel):
    id: str
    kind: PlanKind
    status: PlanStatus
    title: str
    destination: str
    parent_plan_id: str | None = Field(default=None, alias="parentPlanId")
    intent: TravelIntent
    macro_plan: MacroPlan = Field(alias="macroPlan")
    days: list[PlanDay]
    check_report: CheckReport | None = Field(default=None, alias="checkReport")

    model_config = {"populate_by_name": True}
