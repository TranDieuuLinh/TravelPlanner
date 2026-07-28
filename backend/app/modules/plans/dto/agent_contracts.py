from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import (
    CheckReport,
    MacroPlan,
    RegionSnapshotReference,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace


class PlanningAgentName(StrEnum):
    explorer = "explorer"
    planner = "planner"
    finder = "finder"
    checker = "checker"


class PlanningAgentStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"


class PlanningMode(StrEnum):
    main = "main"
    backup = "backup"
    revision = "revision"


class ItineraryItemCategory(StrEnum):
    attraction = "attraction"
    food = "food"
    cafe = "cafe"
    hotel = "hotel"
    transport = "transport"
    free_time = "free_time"
    other = "other"


class TransportMode(StrEnum):
    walk = "walk"
    taxi = "taxi"
    ride_hailing = "ride_hailing"
    bus = "bus"
    train = "train"
    flight = "flight"
    private_car = "private_car"
    mixed = "mixed"
    unknown = "unknown"


class BudgetConfidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class AgentTrace(BaseModel):
    agent: PlanningAgentName
    status: PlanningAgentStatus = PlanningAgentStatus.completed
    summary: str
    notes: list[str] = Field(default_factory=list)


class PlaceCandidateHint(BaseModel):
    name: str
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    source: str = "url_reel"
    source_url: Annotated[str | None, Field(default=None, alias="sourceUrl")]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: int = Field(default=1, ge=1, le=5)
    notes: str | None = None

    model_config = {"populate_by_name": True}


class SelectedPlaceContext(BaseModel):
    name: str
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    priority: int = Field(default=1, ge=1, le=5)
    must_visit: Annotated[bool, Field(default=False, alias="mustVisit")]
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    tags: list[str] = Field(default_factory=list)
    source_refs: Annotated[list[str], Field(alias="sourceRefs")] = Field(
        default_factory=list
    )
    notes: str | None = None

    @property
    def stable_ref(self) -> str:
        return self.place_id or self.name

    model_config = {"populate_by_name": True}


class RegionStatisticsContext(BaseModel):
    region_key: Annotated[str, Field(alias="regionKey")]
    snapshot_ref: Annotated[RegionSnapshotReference, Field(alias="snapshotRef")]
    place_count: Annotated[int, Field(default=0, alias="placeCount")]
    active_place_count: Annotated[int, Field(default=0, alias="activePlaceCount")]
    counts_by_type: Annotated[dict[str, int], Field(alias="countsByType")] = Field(
        default_factory=dict
    )
    tag_counts: Annotated[dict[str, int], Field(alias="tagCounts")] = Field(
        default_factory=dict
    )
    time_of_day_coverage: Annotated[
        dict[str, int], Field(alias="timeOfDayCoverage")
    ] = Field(default_factory=dict)
    typical_duration_by_type: Annotated[
        dict[str, dict[str, int]], Field(alias="typicalDurationByType")
    ] = Field(default_factory=dict)
    tag_time_coverage: Annotated[
        dict[str, dict[str, int]], Field(alias="tagTimeCoverage")
    ] = Field(default_factory=dict)
    tag_duration_profile: Annotated[
        dict[str, dict[str, int]], Field(alias="tagDurationProfile")
    ] = Field(default_factory=dict)
    indoor_outdoor_mix: Annotated[
        dict[str, int], Field(alias="indoorOutdoorMix")
    ] = Field(default_factory=dict)
    weather_sensitivity_counts: Annotated[
        dict[str, int], Field(alias="weatherSensitivityCounts")
    ] = Field(default_factory=dict)
    booking_requirement_counts: Annotated[
        dict[str, int], Field(alias="bookingRequirementCounts")
    ] = Field(default_factory=dict)
    data_quality: Annotated[dict[str, Any], Field(alias="dataQuality")] = Field(
        default_factory=dict
    )
    price_coverage: Annotated[dict[str, int], Field(alias="priceCoverage")] = Field(
        default_factory=dict
    )
    geographic_summary: Annotated[
        dict[str, Any], Field(alias="geographicSummary")
    ] = Field(default_factory=dict)
    area_profiles: Annotated[list[dict[str, Any]], Field(alias="areaProfiles")] = (
        Field(default_factory=list)
    )
    planner_signals: Annotated[dict[str, Any], Field(alias="plannerSignals")] = (
        Field(default_factory=dict)
    )

    model_config = {"populate_by_name": True}


class UnallocatedSelectedPlace(BaseModel):
    place: SelectedPlaceContext
    reason_code: Annotated[str, Field(alias="reasonCode")]
    reason: str

    model_config = {"populate_by_name": True}


class UrlReelSignal(BaseModel):
    url: str
    platform: str | None = None
    extracted_places: Annotated[list[str], Field(alias="extractedPlaces")] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UserPlanningState(BaseModel):
    user_id: Annotated[str | None, Field(alias="userId")] = None
    locale: str = "vi-VN"
    timezone: str = "Asia/Ho_Chi_Minh"
    travel_preferences: Annotated[list[str], Field(alias="travelPreferences")] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PlanWorkingState(BaseModel):
    trip_id: Annotated[str | None, Field(alias="tripId")] = None
    locked_item_ids: Annotated[list[str], Field(alias="lockedItemIds")] = Field(default_factory=list)
    excluded_place_names: Annotated[list[str], Field(alias="excludedPlaceNames")] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PlanningIntent(BaseModel):
    destination: str
    budget_level: Annotated[BudgetLevel, Field(alias="budgetLevel")] = BudgetLevel.balanced
    travel_style: Annotated[str, Field(alias="travelStyle")] = "local"
    pace: TravelPace = TravelPace.balanced
    interests: list[str] = Field(default_factory=list)
    must_visit_places: Annotated[list[str], Field(alias="mustVisitPlaces")] = Field(default_factory=list)
    avoid_places: Annotated[list[str], Field(alias="avoidPlaces")] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    clarifying_questions: Annotated[list[str], Field(alias="clarifyingQuestions")] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MoneyEstimate(BaseModel):
    amount: int = Field(ge=0)
    currency: str = "VND"
    confidence: BudgetConfidence = BudgetConfidence.medium
    notes: str | None = None


class BudgetEnvelope(BaseModel):
    total_budget: Annotated[MoneyEstimate | None, Field(alias="totalBudget")] = None
    per_person_budget: Annotated[MoneyEstimate | None, Field(alias="perPersonBudget")] = None
    include_food: Annotated[bool, Field(alias="includeFood")] = True
    include_transport: Annotated[bool, Field(alias="includeTransport")] = True
    include_hotel: Annotated[bool, Field(alias="includeHotel")] = True
    include_tickets: Annotated[bool, Field(alias="includeTickets")] = True

    model_config = {"populate_by_name": True}


class AccommodationRequirement(BaseModel):
    required: bool = True
    hotel_area: Annotated[str | None, Field(alias="hotelArea")] = None
    check_in_date: Annotated[str | None, Field(alias="checkInDate")] = None
    check_out_date: Annotated[str | None, Field(alias="checkOutDate")] = None
    room_count: Annotated[int, Field(default=1, ge=1, alias="roomCount")]
    guest_count: Annotated[int, Field(default=1, ge=1, alias="guestCount")]
    preferences: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class TransportRequirement(BaseModel):
    required: bool = True
    preferred_modes: Annotated[list[TransportMode], Field(alias="preferredModes")] = Field(default_factory=lambda: [TransportMode.mixed])
    avoid_modes: Annotated[list[TransportMode], Field(alias="avoidModes")] = Field(default_factory=list)
    include_between_places: Annotated[bool, Field(default=True, alias="includeBetweenPlaces")]
    include_arrival_departure: Annotated[bool, Field(default=True, alias="includeArrivalDeparture")]

    model_config = {"populate_by_name": True}


class TripPlanningSpec(BaseModel):
    days: int = Field(ge=1, le=30)
    party_size: Annotated[int, Field(default=1, ge=1, alias="partySize")]
    start_date: Annotated[str | None, Field(default=None, alias="startDate")]
    end_date: Annotated[str | None, Field(default=None, alias="endDate")]
    accommodation: AccommodationRequirement = Field(default_factory=AccommodationRequirement)
    transport: TransportRequirement = Field(default_factory=TransportRequirement)
    budget: BudgetEnvelope = Field(default_factory=BudgetEnvelope)

    model_config = {"populate_by_name": True}


class TransportLeg(BaseModel):
    from_place: Annotated[str, Field(alias="fromPlace")]
    to_place: Annotated[str, Field(alias="toPlace")]
    mode: TransportMode = TransportMode.unknown
    estimated_duration_minutes: Annotated[int | None, Field(default=None, ge=0, alias="estimatedDurationMinutes")]
    estimated_cost: Annotated[MoneyEstimate | None, Field(default=None, alias="estimatedCost")]
    notes: str | None = None

    model_config = {"populate_by_name": True}


class FinalItineraryItem(BaseModel):
    name: str
    category: ItineraryItemCategory
    time_window: Annotated[str, Field(alias="timeWindow")]
    address: str | None = None
    estimated_cost: Annotated[MoneyEstimate | None, Field(default=None, alias="estimatedCost")]
    notes: str | None = None

    model_config = {"populate_by_name": True}


class FinalItineraryDay(BaseModel):
    day: int
    title: str
    hotel: FinalItineraryItem | None = None
    items: list[FinalItineraryItem]
    transport_legs: Annotated[list[TransportLeg], Field(alias="transportLegs")] = Field(default_factory=list)
    day_cost_estimate: Annotated[MoneyEstimate | None, Field(default=None, alias="dayCostEstimate")]

    model_config = {"populate_by_name": True}


class FinalTripCostEstimate(BaseModel):
    accommodation: MoneyEstimate | None = None
    food: MoneyEstimate | None = None
    transport: MoneyEstimate | None = None
    attractions: MoneyEstimate | None = None
    total: MoneyEstimate | None = None


class AgentMacroPlan(MacroPlan):
    pass


class ExplorerAgentInput(BaseModel):
    raw_request: Annotated[str | None, Field(alias="rawRequest")] = None
    destination: str
    place_candidates: Annotated[list[PlaceCandidateHint], Field(alias="placeCandidates")] = Field(default_factory=list)
    url_reel_signals: Annotated[list[UrlReelSignal], Field(alias="urlReelSignals")] = Field(default_factory=list)
    user_state: Annotated[UserPlanningState, Field(alias="userState")] = Field(default_factory=UserPlanningState)
    trip_spec: Annotated[TripPlanningSpec | None, Field(default=None, alias="tripSpec")]

    model_config = {"populate_by_name": True}


class ExplorerAgentOutput(BaseModel):
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    place_candidates: Annotated[list[PlaceCandidateHint], Field(alias="placeCandidates")] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(alias="missingInfoQuestions")] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class PlannerAgentInput(BaseModel):
    mode: PlanningMode = PlanningMode.main
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    region_context: Annotated[RegionStatisticsContext, Field(alias="regionContext")]
    selected_places: Annotated[
        list[SelectedPlaceContext], Field(alias="selectedPlaces")
    ] = Field(default_factory=list)
    place_candidates: Annotated[list[PlaceCandidateHint], Field(alias="placeCandidates")] = Field(default_factory=list)
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    original_macro_plan: Annotated[AgentMacroPlan | None, Field(alias="originalMacroPlan")] = None
    check_report: Annotated[CheckReport | None, Field(alias="checkReport")] = None

    model_config = {"populate_by_name": True}


class PlannerAgentOutput(BaseModel):
    mode: PlanningMode
    macro_plan: Annotated[AgentMacroPlan, Field(alias="macroPlan")]
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    day_briefs_ready: Annotated[bool, Field(alias="dayBriefsReady")] = True
    unallocated_selected_places: Annotated[
        list[UnallocatedSelectedPlace], Field(alias="unallocatedSelectedPlaces")
    ] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class FinderAgentInput(BaseModel):
    mode: PlanningMode = PlanningMode.main
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    macro_plan: Annotated[AgentMacroPlan, Field(alias="macroPlan")]
    place_candidates: Annotated[list[PlaceCandidateHint], Field(alias="placeCandidates")] = Field(default_factory=list)
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    user_state: Annotated[UserPlanningState, Field(alias="userState")] = Field(default_factory=UserPlanningState)

    model_config = {"populate_by_name": True}


class FinderAgentOutput(BaseModel):
    mode: PlanningMode
    final_days: Annotated[list[FinalItineraryDay], Field(alias="finalDays")] = Field(default_factory=list)
    trip_cost_estimate: Annotated[FinalTripCostEstimate | None, Field(default=None, alias="tripCostEstimate")]
    unscheduled_places: Annotated[list[PlaceCandidateHint], Field(alias="unscheduledPlaces")] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class AgentMessage(BaseModel):
    request_id: Annotated[str, Field(alias="requestId")]
    from_agent: Annotated[PlanningAgentName, Field(alias="fromAgent")]
    to_agent: Annotated[PlanningAgentName, Field(alias="toAgent")]
    message_type: Annotated[
        Literal[
            "explorer.input",
            "explorer.output",
            "planner.input",
            "planner.output",
            "finder.input",
            "finder.output",
        ],
        Field(alias="messageType"),
    ]
    payload: dict
    trace: list[AgentTrace] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
