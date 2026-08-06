from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace


class DestinationStay(BaseModel):
    """A day range assigned to a city/region, not a schedulable Place."""

    name: str = Field(min_length=1)
    duration_days: int = Field(ge=1, le=30, alias="durationDays")
    start_day: int = Field(ge=1, le=30, alias="startDay")
    end_day: int = Field(ge=1, le=30, alias="endDay")
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")

    model_config = {"populate_by_name": True}


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
    destination_stays: list[DestinationStay] = Field(
        default_factory=list,
        alias="destinationStays",
    )
    constraint_policy: ConstraintPolicy = Field(
        default_factory=ConstraintPolicy,
        alias="constraintPolicy",
    )
    clarifying_questions: list[str] = Field(default_factory=list, alias="clarifyingQuestions")

    model_config = {"populate_by_name": True}


class DayPartGoals(BaseModel):
    morning: str | None = None
    lunch: str | None = None
    afternoon: str | None = None
    evening: str | None = None


class PreferredTimeWindow(BaseModel):
    """Soft, evidence-backed visit window; never an opening-hours claim."""

    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def end_is_after_start(self) -> "PreferredTimeWindow":
        start_hour, start_minute = (int(value) for value in self.start.split(":"))
        end_hour, end_minute = (int(value) for value in self.end.split(":"))
        if end_hour * 60 + end_minute <= start_hour * 60 + start_minute:
            raise ValueError("preferred time window end must be after start")
        return self


class ExperienceCategory(StrEnum):
    """Trip-wide role understood by TripThemePlanner and PlaceSelector."""

    main_experience = "main_experience"
    meal = "meal"
    supporting_stop = "supporting_stop"
    optional = "optional"
    culture = "culture"
    history = "history"
    nature = "nature"
    food = "food"
    nightlife = "nightlife"
    active = "active"
    outdoor = "outdoor"


class RegionSnapshotReference(BaseModel):
    region_key: str = Field(alias="regionKey")
    snapshot_id: str = Field(alias="snapshotId")
    catalog_version: int = Field(alias="catalogVersion")
    algorithm_version: str = Field(alias="algorithmVersion")
    generated_at: str = Field(alias="generatedAt")

    model_config = {"populate_by_name": True}


class PlaceSelectionDay(BaseModel):
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


class TripThemeRequirement(BaseModel):
    """A must-cover experience at trip scope, never assigned to a day here."""

    theme: str
    focus_tags: list[str] = Field(default_factory=list, alias="focusTags")
    minimum_activities: int = Field(
        default=1,
        ge=1,
        le=30,
        alias="minimumActivities",
    )
    target_region_keys: list[str] = Field(
        default_factory=list,
        alias="targetRegionKeys",
    )
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PlaceSelectionBlueprint(BaseModel):
    title: str
    destination: str
    region_key: str | None = Field(default=None, alias="regionKey")
    trip_themes: list[TripThemeRequirement] = Field(
        default_factory=list,
        alias="tripThemes",
    )
    # Private, deterministic working slots owned by PlaceSelector.
    selection_days: list[PlaceSelectionDay] = Field(
        default_factory=list,
        alias="selectionDays",
    )

    model_config = {"populate_by_name": True}


class PlanItem(BaseModel):
    item_id: str | None = Field(default=None, alias="itemId")
    place_id: str | None = Field(default=None, alias="placeId")
    name: str
    address: str | None = None
    time_window: str = Field(alias="timeWindow")
    place_type: str = Field(alias="placeType")
    timeline_category: Literal["activity", "food", "break"] = Field(
        alias="timelineCategory"
    )
    region_key: str | None = Field(default=None, alias="regionKey")
    role: str | None = None
    source: str = "finder"
    duration_minutes: int | None = Field(default=None, alias="durationMinutes")
    activity_intensity: str | None = Field(
        default=None,
        alias="activityIntensity",
    )
    source_refs: list[str] = Field(
        default_factory=list,
        alias="sourceRefs",
    )
    source_provider: str | None = Field(
        default=None,
        alias="sourceProvider",
    )
    source_import_node_id: int | None = Field(
        default=None, alias="sourceImportNodeId"
    )
    candidate_entity_ids: list[str] = Field(
        default_factory=list, alias="candidateEntityIds"
    )
    selection_method: str | None = Field(default=None, alias="selectionMethod")
    route_score: float | None = Field(default=None, alias="routeScore")
    identity_confidence: str | None = Field(
        default=None, alias="identityConfidence"
    )
    tags: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    personal_notes: str | None = Field(default=None, alias="personalNotes")
    image_urls: list[str] = Field(default_factory=list, alias="imageUrls")
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0, alias="reviewCount")
    opening_hours: list[dict] = Field(default_factory=list, alias="openingHours")
    source_link: str | None = Field(default=None, alias="sourceLink")
    source_order: int | None = Field(default=None, ge=1, alias="sourceOrder")
    source_day: int | None = Field(default=None, ge=1, le=30, alias="sourceDay")
    source_time_hint: str | None = Field(default=None, alias="sourceTimeHint")
    source_activity: str | None = Field(default=None, alias="sourceActivity")
    preferred_time_windows: list[PreferredTimeWindow] = Field(
        default_factory=list,
        alias="preferredTimeWindows",
    )
    locked: bool = False

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def populate_timeline_category(cls, value):
        if not isinstance(value, dict):
            return value
        if "timelineCategory" in value or "timeline_category" in value:
            return value
        data = dict(value)
        place_type = str(
            data.get("placeType", data.get("place_type", ""))
        ).casefold()
        role = str(data.get("role", "")).casefold()
        tags = {str(tag).casefold() for tag in data.get("tags", [])}
        if (
            place_type in {"break", "free_time"}
            or ("break" in role and "breakfast" not in role)
        ):
            category = "break"
        elif (
            place_type
            in {
                "meal",
                "restaurant",
                "cafe",
                "coffee",
                "bakery",
                "fast_food",
                "food_court",
            }
            or "meal" in role
            or bool(
                tags.intersection(
                    {
                        "food",
                        "food_drink",
                        "restaurant",
                        "cafe",
                        "coffee",
                        "bakery",
                    }
                )
            )
        ):
            category = "food"
        else:
            category = "activity"
        data["timelineCategory"] = category
        return data


class PlanTransportOption(BaseModel):
    mode: str
    distance_meters: int = Field(ge=0, alias="distanceMeters")
    estimated_duration_minutes: int = Field(
        ge=0,
        alias="estimatedDurationMinutes",
    )
    geometry_coordinates: list[tuple[float, float]] = Field(
        default_factory=list,
        alias="geometryCoordinates",
    )
    source: str
    verified: bool
    fetched_at: datetime | None = Field(default=None, alias="fetchedAt")
    details: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class PlanTransportLeg(BaseModel):
    from_item_id: str | None = Field(default=None, alias="fromItemId")
    to_item_id: str | None = Field(default=None, alias="toItemId")
    from_place: str = Field(alias="fromPlace")
    to_place: str = Field(alias="toPlace")
    mode: str
    distance_meters: int = Field(ge=0, alias="distanceMeters")
    estimated_duration_minutes: int = Field(
        ge=0,
        alias="estimatedDurationMinutes",
    )
    geometry_coordinates: list[tuple[float, float]] = Field(
        default_factory=list,
        alias="geometryCoordinates",
    )
    source: str = "geodesic_estimate"
    verified: bool = False
    fetched_at: datetime | None = Field(default=None, alias="fetchedAt")
    details: dict = Field(default_factory=dict)
    alternatives: list[PlanTransportOption] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PlanDay(BaseModel):
    day: int
    theme: str
    strategy: str = "anchor_led"
    items: list[PlanItem]
    transport_legs: list[PlanTransportLeg] = Field(
        default_factory=list,
        alias="transportLegs",
    )

    model_config = {"populate_by_name": True}


class UserStatusMetrics(BaseModel):
    physical: int | None = Field(default=None, ge=0, le=100)
    mental: int | None = Field(default=None, ge=0, le=100)
    energy: int | None = Field(default=None, ge=0, le=100)
    mood: int | None = Field(default=None, ge=0, le=100)
    satiety: int | None = Field(default=None, ge=0, le=100)
    hydration: int | None = Field(default=None, ge=0, le=100)


class UserStatusLocation(BaseModel):
    place_id: str | None = Field(default=None, alias="placeId")
    region_key: str | None = Field(default=None, alias="regionKey")
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"populate_by_name": True}


class UserStatusConstraints(BaseModel):
    max_walking_minutes_per_day: int | None = Field(
        default=None,
        ge=0,
        alias="maxWalkingMinutesPerDay",
    )
    max_consecutive_active_minutes: int | None = Field(
        default=None,
        ge=0,
        alias="maxConsecutiveActiveMinutes",
    )
    required_rest_minutes: int | None = Field(
        default=None,
        ge=0,
        alias="requiredRestMinutes",
    )
    allowed_activity_intensities: list[str] = Field(
        default_factory=list,
        alias="allowedActivityIntensities",
    )
    accessibility_needs: list[str] = Field(
        default_factory=list,
        alias="accessibilityNeeds",
    )

    model_config = {"populate_by_name": True}


class UserStatus(BaseModel):
    after_committed_day: int = Field(default=0, ge=0, alias="afterCommittedDay")
    available_at: str | None = Field(default=None, alias="availableAt")
    location: UserStatusLocation | None = None
    active_accommodation_place_id: str | None = Field(
        default=None,
        alias="activeAccommodationPlaceId",
    )
    metrics: UserStatusMetrics = Field(default_factory=UserStatusMetrics)
    constraints: UserStatusConstraints = Field(
        default_factory=UserStatusConstraints
    )

    model_config = {"populate_by_name": True}


class PlaceSelectionUsage(BaseModel):
    activity_minutes: int = Field(default=0, ge=0, alias="activityMinutes")
    travel_minutes: int = Field(default=0, ge=0, alias="travelMinutes")
    walking_minutes: int = Field(default=0, ge=0, alias="walkingMinutes")
    rest_minutes: int = Field(default=0, ge=0, alias="restMinutes")
    place_count: int = Field(default=0, ge=0, alias="placeCount")

    model_config = {"populate_by_name": True}


class PlaceSelectionStatus(BaseModel):
    current_day: int = Field(default=1, ge=1, alias="currentDay")
    current_slot: str | None = Field(default=None, alias="currentSlot")
    current_strategy: str = Field(default="anchor_led", alias="currentStrategy")
    used_place_ids: list[str] = Field(default_factory=list, alias="usedPlaceIds")
    remaining_selected_place_ids: list[str] = Field(
        default_factory=list,
        alias="remainingSelectedPlaceIds",
    )
    locked_item_ids: list[str] = Field(
        default_factory=list,
        alias="lockedItemIds",
    )
    visited_tag_counts: dict[str, int] = Field(
        default_factory=dict,
        alias="visitedTagCounts",
    )
    visited_region_counts: dict[str, int] = Field(
        default_factory=dict,
        alias="visitedRegionCounts",
    )
    used_food_drink_place_types: list[str] = Field(
        default_factory=list,
        alias="usedFoodDrinkPlaceTypes",
    )
    trip_usage: PlaceSelectionUsage = Field(default_factory=PlaceSelectionUsage, alias="tripUsage")
    day_usage: PlaceSelectionUsage = Field(default_factory=PlaceSelectionUsage, alias="dayUsage")
    rejected_candidate_ids: list[str] = Field(
        default_factory=list,
        alias="rejectedCandidateIds",
    )
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UnscheduledPlace(BaseModel):
    place_id: str | None = Field(default=None, alias="placeId")
    name: str
    day: int | None = None
    reason_code: str = Field(alias="reasonCode")
    reason: str
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    place_type: str | None = Field(default=None, alias="placeType")
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")
    source_provider: str | None = Field(default=None, alias="sourceProvider")
    source_activity: str | None = Field(default=None, alias="sourceActivity")
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0, alias="reviewCount")

    model_config = {"populate_by_name": True}


class PlaceSelectionResult(BaseModel):
    days: list[PlanDay]
    final_user_status: UserStatus = Field(alias="finalUserStatus")
    final_plan_status: PlaceSelectionStatus = Field(alias="finalPlanStatus")
    unscheduled_places: list[UnscheduledPlace] = Field(
        default_factory=list,
        alias="unscheduledPlaces",
    )
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CheckIssue(BaseModel):
    code: str
    severity: str
    message: str
    affected_item_ids: list[str] = Field(
        default_factory=list,
        alias="affectedItemIds",
    )
    evidence: list[str] = Field(default_factory=list)
    can_auto_fix: bool = Field(default=False, alias="canAutoFix")
    suggested_action: str | None = Field(
        default=None,
        alias="suggestedAction",
    )

    model_config = {"populate_by_name": True}


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
    trip_themes: list[TripThemeRequirement] = Field(
        default_factory=list,
        alias="tripThemes",
    )
    days: list[PlanDay]
    initial_user_status: UserStatus = Field(
        default_factory=UserStatus,
        alias="initialUserStatus",
    )
    final_user_status: UserStatus = Field(
        default_factory=UserStatus,
        alias="finalUserStatus",
    )
    final_plan_status: PlaceSelectionStatus = Field(
        default_factory=PlaceSelectionStatus,
        alias="finalPlanStatus",
    )
    unscheduled_places: list[UnscheduledPlace] = Field(
        default_factory=list,
        alias="unscheduledPlaces",
    )
    planning_assumptions: list[str] = Field(
        default_factory=list,
        alias="planningAssumptions",
    )
    warnings: list[str] = Field(default_factory=list)
    check_report: CheckReport | None = Field(default=None, alias="checkReport")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_macro_plan(cls, value):
        """Read persisted pre-route-first plans without writing PlaceSelectionBlueprint again."""

        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "tripThemes" not in payload and "trip_themes" not in payload:
            macro = payload.get("macroPlan") or payload.get("macro_plan")
            if isinstance(macro, dict):
                payload["tripThemes"] = (
                    macro.get("tripThemes") or macro.get("trip_themes") or []
                )
        payload.pop("macroPlan", None)
        payload.pop("macro_plan", None)
        return payload

    model_config = {"populate_by_name": True}
