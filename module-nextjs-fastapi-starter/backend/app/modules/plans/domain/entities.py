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


class DayBrief(BaseModel):
    day: int
    theme: str
    target_area: str = Field(alias="targetArea")
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MacroPlan(BaseModel):
    title: str
    destination: str
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
