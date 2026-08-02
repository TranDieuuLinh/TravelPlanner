from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.plans.domain.entities import (
    CheckReport,
    FinderPlanStatus,
    MacroPlan,
    PlanDay,
    RegionSnapshotReference,
    UnscheduledPlace,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.preferences.schema import LongTermPreferenceProfile


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
    nature = "nature"
    culture = "culture"
    shopping = "shopping"
    nightlife = "nightlife"
    wellness = "wellness"
    adventure = "adventure"
    beach = "beach"
    family = "family"
    cemetery = "cemetery"
    other = "other"


class PlacePreferenceLevel(StrEnum):
    mentioned = "mentioned"
    preferred = "preferred"
    must_visit = "must_visit"


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
    category: ItineraryItemCategory = ItineraryItemCategory.other
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    address: str | None = None
    search_region: Annotated[
        str | None,
        Field(default=None, alias="searchRegion"),
    ]
    latitude: Annotated[float | None, Field(default=None, ge=-90, le=90)]
    longitude: Annotated[float | None, Field(default=None, ge=-180, le=180)]
    source: str = "url_reel"
    source_url: Annotated[str | None, Field(default=None, alias="sourceUrl")]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: int = Field(default=1, ge=1, le=5)
    preference_level: Annotated[
        PlacePreferenceLevel,
        Field(default=PlacePreferenceLevel.preferred, alias="preferenceLevel"),
    ]
    attributes: list[str] = Field(default_factory=list)
    notes: str | None = None
    source_evidence: Annotated[
        dict[str, str],
        Field(default_factory=dict, alias="sourceEvidence"),
    ]
    source_order: Annotated[int | None, Field(default=None, ge=1, alias="sourceOrder")]
    source_day: Annotated[int | None, Field(default=None, ge=1, le=30, alias="sourceDay")]
    source_time_hint: Annotated[str | None, Field(default=None, alias="sourceTimeHint")]
    source_activity: Annotated[str | None, Field(default=None, alias="sourceActivity")]
    source_duration_minutes: Annotated[
        int | None,
        Field(default=None, ge=15, le=720, alias="sourceDurationMinutes"),
    ]

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> "PlaceCandidateHint":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class SelectedPlaceContext(BaseModel):
    name: str
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    address: str | None = None
    priority: int = Field(default=1, ge=1, le=5)
    must_visit: Annotated[bool, Field(default=False, alias="mustVisit")]
    preference_level: Annotated[
        PlacePreferenceLevel,
        Field(default=PlacePreferenceLevel.preferred, alias="preferenceLevel"),
    ]
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    latitude: Annotated[float | None, Field(default=None, ge=-90, le=90)]
    longitude: Annotated[float | None, Field(default=None, ge=-180, le=180)]
    tags: list[str] = Field(default_factory=list)
    source_refs: Annotated[list[str], Field(alias="sourceRefs")] = Field(
        default_factory=list
    )
    source_provider: Annotated[
        str | None,
        Field(default=None, alias="sourceProvider"),
    ]
    notes: str | None = None
    source_order: Annotated[int | None, Field(default=None, ge=1, alias="sourceOrder")]
    source_day: Annotated[int | None, Field(default=None, ge=1, le=30, alias="sourceDay")]
    source_time_hint: Annotated[str | None, Field(default=None, alias="sourceTimeHint")]
    source_activity: Annotated[str | None, Field(default=None, alias="sourceActivity")]
    source_duration_minutes: Annotated[
        int | None,
        Field(default=None, ge=15, le=720, alias="sourceDurationMinutes"),
    ]

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
    planner_eligible: Annotated[
        dict[str, Any], Field(alias="plannerEligible")
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
    extracted_place_details: Annotated[list[PlaceCandidateHint], Field(alias="extractedPlaceDetails")] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UserPlanningState(BaseModel):
    user_id: Annotated[str | None, Field(alias="userId")] = None
    locale: str = "vi-VN"
    timezone: str = "Asia/Ho_Chi_Minh"
    travel_style: Annotated[str, Field(alias="travelStyle")] = "local"
    travel_preferences: Annotated[list[str], Field(alias="travelPreferences")] = Field(default_factory=list)
    preference_profile: Annotated[
        LongTermPreferenceProfile,
        Field(default_factory=LongTermPreferenceProfile, alias="preferenceProfile"),
    ]

    model_config = {"populate_by_name": True}


class PlanWorkingState(BaseModel):
    trip_id: Annotated[str | None, Field(alias="tripId")] = None
    locked_item_ids: Annotated[list[str], Field(alias="lockedItemIds")] = Field(default_factory=list)
    excluded_place_names: Annotated[list[str], Field(alias="excludedPlaceNames")] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PlanningIntent(BaseModel):
    destination: str
    travel_style: Annotated[str, Field(alias="travelStyle")] = "local"
    pace: TravelPace = TravelPace.balanced
    interests: list[str] = Field(default_factory=list)
    must_visit_places: Annotated[list[str], Field(alias="mustVisitPlaces")] = Field(default_factory=list)
    avoid_places: Annotated[list[str], Field(alias="avoidPlaces")] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    constraint_policy: Annotated[
        ConstraintPolicy,
        Field(default_factory=ConstraintPolicy, alias="constraintPolicy"),
    ]
    clarifying_questions: Annotated[list[str], Field(alias="clarifyingQuestions")] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MoneyEstimate(BaseModel):
    amount: int = Field(ge=0)
    currency: str = "VND"
    confidence: BudgetConfidence = BudgetConfidence.medium
    notes: str | None = None


class BudgetEnvelope(BaseModel):
    target_amount: Annotated[
        int | None, Field(default=None, ge=0, alias="targetAmount")
    ]
    currency: str = "VND"
    level: BudgetLevel = BudgetLevel.medium

    model_config = {"populate_by_name": True}

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO 4217 code.")
        return normalized


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
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(alias="missingInfoQuestions")] = Field(default_factory=list)
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class PlannerThemeResearchQuery(BaseModel):
    theme: str = Field(min_length=1, max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=6)
    preferred_region_key: Annotated[
        str | None,
        Field(default=None, alias="preferredRegionKey"),
    ]
    rationale: str = Field(min_length=1, max_length=500)

    model_config = {"populate_by_name": True}


class PlannerResearchDraft(BaseModel):
    journey_style: Annotated[
        Literal["local_base", "hub_and_spoke", "multi_base", "road_trip"],
        Field(alias="journeyStyle"),
    ] = "local_base"
    variety_strategy: Annotated[
        str,
        Field(min_length=1, max_length=800, alias="varietyStrategy"),
    ]
    theme_queries: Annotated[
        list[PlannerThemeResearchQuery],
        Field(min_length=1, max_length=8, alias="themeQueries"),
    ]
    expand_beyond_root: Annotated[
        bool,
        Field(default=False, alias="expandBeyondRoot"),
    ]
    nearby_capabilities: Annotated[
        list[str],
        Field(default_factory=list, max_length=8, alias="nearbyCapabilities"),
    ]
    max_distance_km: Annotated[
        float,
        Field(default=120.0, ge=1, le=500, alias="maxDistanceKm"),
    ]

    model_config = {"populate_by_name": True}


class PlannerCapabilityEvidence(BaseModel):
    theme: str
    capability: str
    supported: bool
    active_place_count: Annotated[int, Field(ge=0, alias="activePlaceCount")]
    region_keys: Annotated[list[str], Field(alias="regionKeys")] = Field(
        default_factory=list
    )
    sample_places: Annotated[list[dict[str, Any]], Field(alias="samplePlaces")] = (
        Field(default_factory=list)
    )
    confidence: Literal["none", "low", "medium", "high"] = "none"

    model_config = {"populate_by_name": True}


class PlannerNearbyRegionEvidence(BaseModel):
    region_key: Annotated[str, Field(alias="regionKey")]
    distance_km: Annotated[float, Field(ge=0, alias="distanceKm")]
    active_place_count: Annotated[int, Field(ge=0, alias="activePlaceCount")]
    matching_capabilities: Annotated[
        list[str],
        Field(alias="matchingCapabilities"),
    ] = Field(default_factory=list)
    sample_places: Annotated[list[dict[str, Any]], Field(alias="samplePlaces")] = (
        Field(default_factory=list)
    )

    model_config = {"populate_by_name": True}


class PlannerThemeExperienceEvidence(BaseModel):
    """Knowledge-graph expansion for one proposed journey theme."""

    theme: str
    matched_node_ids: Annotated[list[str], Field(alias="matchedNodeIds")] = Field(
        default_factory=list
    )
    experience_node_ids: Annotated[
        list[str], Field(alias="experienceNodeIds")
    ] = Field(default_factory=list)
    query_terms: Annotated[list[str], Field(alias="queryTerms")] = Field(
        default_factory=list
    )
    categories: list[str] = Field(default_factory=list)
    diversity_groups: Annotated[
        list[str], Field(alias="diversityGroups")
    ] = Field(default_factory=list)
    region_keys: Annotated[list[str], Field(alias="regionKeys")] = Field(
        default_factory=list
    )

    model_config = {"populate_by_name": True}


class PlannerVerifiedResearch(BaseModel):
    capability_evidence: Annotated[
        list[PlannerCapabilityEvidence],
        Field(alias="capabilityEvidence"),
    ] = Field(default_factory=list)
    nearby_regions: Annotated[
        list[PlannerNearbyRegionEvidence],
        Field(alias="nearbyRegions"),
    ] = Field(default_factory=list)
    experience_evidence: Annotated[
        list[PlannerThemeExperienceEvidence],
        Field(alias="experienceEvidence"),
    ] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class TourismZoneAnchor(BaseModel):
    place_id: Annotated[str, Field(alias="placeId")]
    name: str
    category: str
    latitude: float
    longitude: float
    rating: float | None = None
    review_count: Annotated[int, Field(default=0, alias="reviewCount")]
    popularity_score: Annotated[float, Field(alias="popularityScore")]

    model_config = {"populate_by_name": True}


class TourismZoneEvidence(BaseModel):
    zone_id: Annotated[str, Field(alias="zoneId")]
    region_key: Annotated[str, Field(alias="regionKey")]
    center_latitude: Annotated[float, Field(alias="centerLatitude")]
    center_longitude: Annotated[float, Field(alias="centerLongitude")]
    radius_meters: Annotated[int, Field(ge=500, le=20_000, alias="radiusMeters")]
    capabilities: list[str] = Field(default_factory=list)
    primary_categories: Annotated[
        list[str],
        Field(default_factory=list, alias="primaryCategories"),
    ]
    category_coverage: Annotated[
        dict[str, int],
        Field(default_factory=dict, alias="categoryCoverage"),
    ]
    anchor_places: Annotated[
        list[TourismZoneAnchor],
        Field(default_factory=list, alias="anchorPlaces"),
    ]
    place_count: Annotated[int, Field(ge=0, alias="placeCount")]
    compactness_score: Annotated[float, Field(ge=0, le=1, alias="compactnessScore")]
    popularity_score: Annotated[float, Field(ge=0, le=1, alias="popularityScore")]

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
    preference_profile: Annotated[
        LongTermPreferenceProfile,
        Field(default_factory=LongTermPreferenceProfile, alias="preferenceProfile"),
    ]
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    original_macro_plan: Annotated[AgentMacroPlan | None, Field(alias="originalMacroPlan")] = None
    check_report: Annotated[CheckReport | None, Field(alias="checkReport")] = None
    # === Research Tools Results ===
    # Optional tool results that can be pre-populated before calling planner
    region_overview: Annotated[
        dict | None,
        Field(
            alias="regionOverview",
            description="Pre-computed region overview statistics from region_overview tool"
        )
    ] = Field(default=None)
    constraint_research: Annotated[
        dict | None,
        Field(
            alias="constraintResearch",
            description="Pre-computed constraint research results from constraint_research tool"
        )
    ] = Field(default=None)
    festival_discovery: Annotated[
        dict | None,
        Field(
            alias="festivalDiscovery",
            description="Pre-computed festival discovery results from festival_discovery tool"
        )
    ] = Field(default=None)
    tourism_zones: Annotated[
        list[TourismZoneEvidence],
        Field(default_factory=list, alias="tourismZones"),
    ]

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
    tourism_zones: Annotated[
        list[TourismZoneEvidence],
        Field(default_factory=list, alias="tourismZones"),
    ]
    trace: AgentTrace

    model_config = {"populate_by_name": True}


class PlannerMacroPlanDraft(BaseModel):
    macro_plan: Annotated[AgentMacroPlan, Field(alias="macroPlan")]
    unallocated_selected_places: Annotated[
        list[UnallocatedSelectedPlace], Field(alias="unallocatedSelectedPlaces")
    ] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class FinderAgentInput(BaseModel):
    mode: PlanningMode = PlanningMode.main
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    macro_plan: Annotated[AgentMacroPlan, Field(alias="macroPlan")]
    selected_places: Annotated[
        list[SelectedPlaceContext], Field(alias="selectedPlaces")
    ] = Field(default_factory=list)
    place_candidates: Annotated[list[PlaceCandidateHint], Field(alias="placeCandidates")] = Field(default_factory=list)
    plan_state: Annotated[PlanWorkingState, Field(alias="planState")] = Field(default_factory=PlanWorkingState)
    user_state: Annotated[UserPlanningState, Field(alias="userState")] = Field(default_factory=UserPlanningState)
    user_status: Annotated[UserStatus, Field(alias="userStatus")] = Field(
        default_factory=UserStatus
    )
    finder_plan_status: Annotated[
        FinderPlanStatus, Field(alias="finderPlanStatus")
    ] = Field(default_factory=FinderPlanStatus)
    allow_finder_suggestions: Annotated[
        bool,
        Field(default=True, alias="allowFinderSuggestions"),
    ]
    tourism_zones: Annotated[
        list[TourismZoneEvidence],
        Field(default_factory=list, alias="tourismZones"),
    ]

    model_config = {"populate_by_name": True}


class FinderAgentOutput(BaseModel):
    mode: PlanningMode
    final_days: Annotated[list[PlanDay], Field(alias="finalDays")] = Field(
        default_factory=list
    )
    trip_cost_estimate: Annotated[FinalTripCostEstimate | None, Field(default=None, alias="tripCostEstimate")]
    unscheduled_places: Annotated[
        list[UnscheduledPlace], Field(alias="unscheduledPlaces")
    ] = Field(default_factory=list)
    final_user_status: Annotated[UserStatus, Field(alias="finalUserStatus")] = Field(
        default_factory=UserStatus
    )
    final_plan_status: Annotated[
        FinderPlanStatus, Field(alias="finalPlanStatus")
    ] = Field(default_factory=FinderPlanStatus)
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
