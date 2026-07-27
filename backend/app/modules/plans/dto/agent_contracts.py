from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import CheckReport, MacroPlan, PlanDay, TravelIntent


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


class SelectedPlaceHint(BaseModel):
    name: str
    place_id: Annotated[str | None, Field(alias="placeId")] = None
    source: str = "user"
    priority: int = Field(default=1, ge=1, le=5)
    notes: str | None = None

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


class FinalPlanRequirements(BaseModel):
    include_day_by_day: Annotated[bool, Field(default=True, alias="includeDayByDay")]
    include_attractions: Annotated[bool, Field(default=True, alias="includeAttractions")]
    include_food: Annotated[bool, Field(default=True, alias="includeFood")]
    include_cafes: Annotated[bool, Field(default=True, alias="includeCafes")]
    include_hotel: Annotated[bool, Field(default=True, alias="includeHotel")]
    include_transport: Annotated[bool, Field(default=True, alias="includeTransport")]
    include_price_estimate: Annotated[bool, Field(default=True, alias="includePriceEstimate")]
    required_item_categories: Annotated[list[ItineraryItemCategory], Field(alias="requiredItemCategories")] = Field(
        default_factory=lambda: [
            ItineraryItemCategory.attraction,
            ItineraryItemCategory.food,
            ItineraryItemCategory.cafe,
            ItineraryItemCategory.hotel,
            ItineraryItemCategory.transport,
        ]
    )

    model_config = {"populate_by_name": True}


class TripPlanningSpec(BaseModel):
    days: int = Field(ge=1, le=30)
    party_size: Annotated[int, Field(default=1, ge=1, alias="partySize")]
    start_date: Annotated[str | None, Field(default=None, alias="startDate")]
    end_date: Annotated[str | None, Field(default=None, alias="endDate")]
    accommodation: AccommodationRequirement = Field(default_factory=AccommodationRequirement)
    transport: TransportRequirement = Field(default_factory=TransportRequirement)
    budget: BudgetEnvelope = Field(default_factory=BudgetEnvelope)
    final_plan_requirements: Annotated[FinalPlanRequirements, Field(alias="finalPlanRequirements")] = Field(
        default_factory=FinalPlanRequirements
    )

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


class ExplorerAgentInput(BaseModel):
    raw_request: Annotated[str | None, Field(alias="rawRequest")] = None
    destination: str
    days: int = Field(ge=1, le=30)
    selected_places: Annotated[list[SelectedPlaceHint], Field(alias="selectedPlaces")] = Field(default_factory=list)
    url_reel_signals: Annotated[list[UrlReelSignal], Field(alias="urlReelSignals")] = Field(default_factory=list)
    user_state: Annotated[UserPlanningState, Field(alias="userState")] = Field(default_factory=UserPlanningState)
    trip_spec: Annotated[TripPlanningSpec | None, Field(default=None, alias="tripSpec")]

    model_config = {"populate_by_name": True}


class ExplorerAgentOutput(BaseModel):
    intent: TravelIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    final_plan_requirements: Annotated[FinalPlanRequirements, Field(alias="finalPlanRequirements")]
    selected_places: Annotated[list[SelectedPlaceHint], Field(alias="selectedPlaces")] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(alias="missingInfoQuestions")] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class PlannerAgentInput(BaseModel):
    mode: PlanningMode = PlanningMode.main
    intent: TravelIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    selected_places: Annotated[list[SelectedPlaceHint], Field(alias="selectedPlaces")] = Field(default_factory=list)
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    original_macro_plan: Annotated[MacroPlan | None, Field(alias="originalMacroPlan")] = None
    check_report: Annotated[CheckReport | None, Field(alias="checkReport")] = None

    model_config = {"populate_by_name": True}


class PlannerAgentOutput(BaseModel):
    mode: PlanningMode
    macro_plan: Annotated[MacroPlan, Field(alias="macroPlan")]
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    day_briefs_ready: Annotated[bool, Field(alias="dayBriefsReady")] = True
    assumptions: list[str] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class FinderAgentInput(BaseModel):
    mode: PlanningMode = PlanningMode.main
    intent: TravelIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    macro_plan: Annotated[MacroPlan, Field(alias="macroPlan")]
    selected_places: Annotated[list[SelectedPlaceHint], Field(alias="selectedPlaces")] = Field(default_factory=list)
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    user_state: Annotated[UserPlanningState, Field(alias="userState")] = Field(default_factory=UserPlanningState)

    model_config = {"populate_by_name": True}


class FinderAgentOutput(BaseModel):
    mode: PlanningMode
    days: list[PlanDay]
    final_days: Annotated[list[FinalItineraryDay], Field(alias="finalDays")] = Field(default_factory=list)
    trip_cost_estimate: Annotated[FinalTripCostEstimate | None, Field(default=None, alias="tripCostEstimate")]
    unscheduled_places: Annotated[list[SelectedPlaceHint], Field(alias="unscheduledPlaces")] = Field(default_factory=list)
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
