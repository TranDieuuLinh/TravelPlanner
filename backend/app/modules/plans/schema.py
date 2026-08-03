from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import (
    CheckReport,
    Plan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import PlanningIntent, TripPlanningSpec
from app.modules.plans.dto.agent_contracts import PlacePreferenceLevel
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.plans.timing import PlanTimingReport


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
    address: str | None = None
    priority: Annotated[int, Field(default=1, ge=1, le=5)]
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
    personal_notes: Annotated[
        str | None,
        Field(default=None, alias="personalNotes"),
    ]
    image_urls: Annotated[list[str], Field(alias="imageUrls")] = Field(
        default_factory=list
    )
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: Annotated[
        int | None,
        Field(default=None, ge=0, alias="reviewCount"),
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
    intake_id: Annotated[str | None, Field(default=None, alias="intakeId")]
    user_id: Annotated[str | None, Field(default=None, alias="userId")]
    selected_places: Annotated[
        list[SelectedPlaceCreate],
        Field(alias="selectedPlaces"),
    ] = Field(default_factory=list)
    candidate_reviews: Annotated[
        list[PlaceCandidateReview],
        Field(default_factory=list, alias="candidateReviews"),
    ]
    region_key: Annotated[str | None, Field(default=None, alias="regionKey")]
    user_status: Annotated[UserStatus, Field(alias="userStatus")] = Field(
        default_factory=UserStatus
    )
    preference_profile: Annotated[
        LongTermPreferenceProfile,
        Field(default_factory=LongTermPreferenceProfile, alias="preferenceProfile"),
    ]
    allow_finder_suggestions: Annotated[
        bool,
        Field(default=True, alias="allowFinderSuggestions"),
    ]
    expand_days_to_fit_selected_places: Annotated[
        bool,
        Field(default=False, alias="expandDaysToFitSelectedPlaces"),
    ]

    model_config = {"populate_by_name": True}


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


class RouteCoordinate(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class RouteDestination(RouteCoordinate):
    item_id: Annotated[str | None, Field(default=None, alias="itemId")]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    address: Annotated[str | None, Field(default=None, max_length=1000)]
    time_window: Annotated[
        str | None,
        Field(default=None, min_length=11, max_length=32, alias="timeWindow"),
    ]

    model_config = {"populate_by_name": True}


class CurrentLocationRouteCreate(BaseModel):
    origin: RouteCoordinate
    destination: RouteDestination
    departure_time: Annotated[
        datetime | None,
        Field(default=None, alias="departureTime"),
    ]
    preferred_modes: Annotated[
        list[str],
        Field(default_factory=list, alias="preferredModes"),
    ]
    avoid_modes: Annotated[
        list[str],
        Field(default_factory=list, alias="avoidModes"),
    ]

    model_config = {"populate_by_name": True}


class DayDirectionsCreate(BaseModel):
    origin: RouteCoordinate
    destinations: Annotated[
        list[RouteDestination],
        Field(min_length=1, max_length=30),
    ]
    requested_mode: Annotated[
        Literal["walk", "car", "bus"] | None,
        Field(default=None, alias="requestedMode"),
    ]
    departure_time: Annotated[
        datetime | None,
        Field(default=None, alias="departureTime"),
    ]

    model_config = {"populate_by_name": True}


TravelIntentRead = TravelIntent
PlanRead = Plan
CheckReportRead = CheckReport


class PlanGenerationRead(BaseModel):
    plan: PlanRead
    timing_report: Annotated[PlanTimingReport, Field(alias="timingReport")]

    model_config = {"populate_by_name": True}


class PlanBundleRead(BaseModel):
    main_plan: Annotated[PlanRead, Field(alias="mainPlan")]
    backup_plan: Annotated[PlanRead, Field(alias="backupPlan")]
    validation: CheckReportRead

    model_config = {"populate_by_name": True}
