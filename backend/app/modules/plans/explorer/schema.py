from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.plans.dto.agent_contracts import (
    ItineraryItemCategory,
    PlaceCandidateHint,
    PlacePreferenceLevel,
    PlanningIntent,
    TripPlanningSpec,
    UserPlanningState,
)
from app.modules.plans.domain.enums import BudgetLevel
from app.modules.preferences.schema import PreferenceSnapshot


class ExploreAccommodationInput(BaseModel):
    required: bool | None = None
    hotel_area: Annotated[str | None, Field(default=None, alias="hotelArea")]
    check_in_date: Annotated[str | None, Field(default=None, alias="checkInDate")]
    check_out_date: Annotated[str | None, Field(default=None, alias="checkOutDate")]
    room_count: Annotated[int | None, Field(default=None, ge=1, alias="roomCount")]
    guest_count: Annotated[int | None, Field(default=None, ge=1, alias="guestCount")]
    preferences: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ExploreTransportInput(BaseModel):
    required: bool | None = None
    preferred_modes: Annotated[list[str], Field(default_factory=list, alias="preferredModes")]
    avoid_modes: Annotated[list[str], Field(default_factory=list, alias="avoidModes")]
    include_between_places: Annotated[bool | None, Field(default=None, alias="includeBetweenPlaces")]
    include_arrival_departure: Annotated[bool | None, Field(default=None, alias="includeArrivalDeparture")]

    model_config = {"populate_by_name": True}


class ExploreBudgetInput(BaseModel):
    target_amount: Annotated[
        int | None, Field(default=None, ge=0, alias="targetAmount")
    ]
    currency: str = "VND"
    level: BudgetLevel = BudgetLevel.medium

    model_config = {"populate_by_name": True}


class ExploreTripSpecInput(BaseModel):
    days: Annotated[int | None, Field(default=None, ge=1, le=30)]
    party_size: Annotated[int | None, Field(default=None, ge=1, alias="partySize")]
    start_date: Annotated[str | None, Field(default=None, alias="startDate")]
    end_date: Annotated[str | None, Field(default=None, alias="endDate")]
    accommodation: ExploreAccommodationInput = Field(default_factory=ExploreAccommodationInput)
    transport: ExploreTransportInput = Field(default_factory=ExploreTransportInput)
    budget: ExploreBudgetInput = Field(default_factory=ExploreBudgetInput)

    model_config = {"populate_by_name": True}


class ExploreImageContext(BaseModel):
    file_name: Annotated[str, Field(alias="fileName")]
    mime_type: Annotated[str, Field(alias="mimeType")]
    ocr_text: Annotated[str, Field(default="", alias="ocrText")]
    status: str = "ok"
    error: str | None = None

    model_config = {"populate_by_name": True}


class FullExploreRequest(BaseModel):
    raw_request: Annotated[str, Field(min_length=1, alias="rawRequest")]
    destination: Annotated[str, Field(min_length=1)]
    urls: list[str] = Field(default_factory=list)
    place_candidates: Annotated[list[PlaceCandidateHint], Field(default_factory=list, alias="placeCandidates")]
    user_state: Annotated[UserPlanningState, Field(default_factory=UserPlanningState, alias="userState")]
    trip_spec: Annotated[ExploreTripSpecInput, Field(default_factory=ExploreTripSpecInput, alias="tripSpec")]
    image_contexts: Annotated[list["ExploreImageContext"], Field(default_factory=list, alias="imageContexts")]

    model_config = {"populate_by_name": True}


class PlaceCandidateSourceType(StrEnum):
    user_prompt = "user_prompt"
    ocr = "ocr"
    url = "url"


class PlaceCandidateSource(BaseModel):
    type: PlaceCandidateSourceType
    url: str | None = None


class UnifiedPlaceCandidate(BaseModel):
    name: str = Field(min_length=1)
    search_names: Annotated[
        list[str],
        Field(default_factory=list, alias="searchNames"),
    ]
    category: ItineraryItemCategory = ItineraryItemCategory.other
    address_hint: Annotated[str | None, Field(default=None, alias="addressHint")]
    search_region: Annotated[
        str | None,
        Field(default=None, alias="searchRegion"),
    ]
    sources: list[PlaceCandidateSource] = Field(default_factory=list)
    source_evidence: Annotated[
        dict[str, str],
        Field(default_factory=dict, alias="sourceEvidence"),
    ]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: int = Field(default=1, ge=1, le=5)
    preference_level: Annotated[
        PlacePreferenceLevel,
        Field(default=PlacePreferenceLevel.preferred, alias="preferenceLevel"),
    ]
    attributes: list[str] = Field(default_factory=list)
    notes: str | None = None
    source_order: Annotated[int | None, Field(default=None, ge=1, alias="sourceOrder")]
    source_day: Annotated[int | None, Field(default=None, ge=1, le=30, alias="sourceDay")]
    source_time_hint: Annotated[str | None, Field(default=None, alias="sourceTimeHint")]
    source_activity: Annotated[str | None, Field(default=None, alias="sourceActivity")]
    source_duration_minutes: Annotated[
        int | None,
        Field(default=None, ge=15, le=720, alias="sourceDurationMinutes"),
    ]

    model_config = {"populate_by_name": True}


class ExplorerContextResponse(BaseModel):
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(default_factory=list, alias="missingInfoQuestions")]
    preference_snapshot: Annotated[
        PreferenceSnapshot,
        Field(default_factory=PreferenceSnapshot, alias="preferenceSnapshot"),
    ]

    model_config = {"populate_by_name": True}


class PlaceCandidatesResponse(BaseModel):
    place_candidates: Annotated[
        list[UnifiedPlaceCandidate],
        Field(default_factory=list, alias="placeCandidates"),
    ]

    model_config = {"populate_by_name": True}


class ExploreBundleDraft(BaseModel):
    explorer: ExplorerContextResponse
    places: PlaceCandidatesResponse


class ExploreIntakeResponse(BaseModel):
    intake_id: Annotated[str, Field(alias="intakeId")]
    user_id: Annotated[str | None, Field(default=None, alias="userId")]
    explorer: ExplorerContextResponse
    allow_finder_suggestions: Annotated[
        bool,
        Field(default=True, alias="allowFinderSuggestions"),
    ]

    model_config = {"populate_by_name": True}
