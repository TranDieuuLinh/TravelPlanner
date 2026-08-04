from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

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
    destination: str = ""
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


class IntakeInputCompleteness(StrEnum):
    """How complete the original Explorer input was."""

    vague = "vague"
    partial = "partial"
    anchor = "anchor"
    complete = "complete"


class MissingFieldInfo(BaseModel):
    """Metadata for a planning field absent from the original input."""

    field: str
    was_provided: Annotated[bool, Field(default=False, alias="wasProvided")]
    inferred_source: Annotated[
        str | None,
        Field(default=None, alias="inferredSource"),
    ]

    model_config = {"populate_by_name": True}


class PlaceCandidateSource(BaseModel):
    type: PlaceCandidateSourceType
    url: str | None = None


class ObservedPlaceAlias(BaseModel):
    """A name variant that was actually present in source evidence."""

    value: str = Field(min_length=1)
    source: Literal["metadata", "caption", "transcript", "stt", "ocr", "user"]


class GeneratedLookupAlias(BaseModel):
    """A derived lookup name; this is never source provenance."""

    value: str = Field(min_length=1)
    language: Literal["vi", "en", "und"] = "und"
    generator: Literal["normalizer", "llm"] = "llm"
    version: str = "alias-v1"


class PlaceMatchOption(BaseModel):
    """A ranked Place identity considered by a resolver for one candidate."""

    rank: int = Field(ge=1)
    match_source: Annotated[
        Literal["url_snapshot", "verified_alias", "places_db", "external_provider"],
        Field(alias="matchSource"),
    ]
    provider: str
    place_id: Annotated[str | None, Field(default=None, alias="placeId")]
    external_id: Annotated[str | None, Field(default=None, alias="externalId")]
    name: str
    selected: bool = False
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_components: Annotated[
        dict[str, float],
        Field(default_factory=dict, alias="scoreComponents"),
    ]
    rejection_reasons: Annotated[
        list[str],
        Field(default_factory=list, alias="rejectionReasons"),
    ]
    fetched_at: Annotated[str | None, Field(default=None, alias="fetchedAt")]

    model_config = {"populate_by_name": True}


class UnifiedPlaceCandidate(BaseModel):
    name: str = Field(min_length=1)
    original_name: Annotated[
        str | None,
        Field(default=None, alias="originalName"),
    ]
    english_names: Annotated[
        list[str],
        Field(default_factory=list, alias="englishNames"),
    ]
    vietnamese_names: Annotated[
        list[str],
        Field(default_factory=list, alias="vietnameseNames"),
    ]
    alternate_names: Annotated[
        list[str],
        Field(default_factory=list, alias="alternateNames"),
    ]
    search_names: Annotated[
        list[str],
        Field(default_factory=list, alias="searchNames"),
    ]
    observed_aliases: Annotated[
        list[ObservedPlaceAlias],
        Field(default_factory=list, alias="observedAliases"),
    ]
    generated_lookup_aliases: Annotated[
        list[GeneratedLookupAlias],
        Field(default_factory=list, alias="generatedLookupAliases"),
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
    entity_type: Annotated[
        Literal["venue", "sub_place"],
        Field(default="venue", alias="entityType"),
    ]
    parent_place: Annotated[
        str | None,
        Field(default=None, alias="parentPlace"),
    ]
    authority: Literal["high", "medium", "low"] = "medium"

    model_config = {"populate_by_name": True}


class PlaceCandidateReview(BaseModel):
    candidate_id: Annotated[str, Field(alias="candidateId")]
    name: str
    category: ItineraryItemCategory = ItineraryItemCategory.other
    status: Literal["resolved", "needs_review", "merged", "ignored"]
    resolution_reason: Annotated[
        str | None,
        Field(default=None, alias="resolutionReason"),
    ]
    provider: str | None = None
    resolved_name: Annotated[
        str | None,
        Field(default=None, alias="resolvedName"),
    ]
    verified_aliases: Annotated[
        list[str],
        Field(default_factory=list, alias="verifiedAliases"),
    ]
    verified_vietnamese_aliases: Annotated[
        list[str],
        Field(default_factory=list, alias="verifiedVietnameseAliases"),
    ]
    observed_aliases: Annotated[
        list[ObservedPlaceAlias],
        Field(default_factory=list, alias="observedAliases"),
    ]
    generated_lookup_aliases: Annotated[
        list[GeneratedLookupAlias],
        Field(default_factory=list, alias="generatedLookupAliases"),
    ]
    top_matches: Annotated[
        list[PlaceMatchOption],
        Field(default_factory=list, alias="topMatches"),
    ]
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    has_representative_location: Annotated[
        bool,
        Field(default=False, alias="hasRepresentativeLocation"),
    ]
    search_region: Annotated[
        str | None,
        Field(default=None, alias="searchRegion"),
    ]
    source_urls: Annotated[
        list[str],
        Field(default_factory=list, alias="sourceUrls"),
    ]
    source_order: Annotated[
        int | None,
        Field(default=None, ge=1, alias="sourceOrder"),
    ]
    source_day: Annotated[
        int | None,
        Field(default=None, ge=1, le=30, alias="sourceDay"),
    ]
    source_time_hint: Annotated[
        str | None,
        Field(default=None, alias="sourceTimeHint"),
    ]
    source_activity: Annotated[
        str | None,
        Field(default=None, alias="sourceActivity"),
    ]
    source_duration_minutes: Annotated[
        int | None,
        Field(default=None, ge=15, le=720, alias="sourceDurationMinutes"),
    ]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_confidence: Annotated[
        float,
        Field(default=0.0, ge=0.0, le=1.0, alias="extractionConfidence"),
    ]
    resolution_confidence: Annotated[
        float,
        Field(default=0.0, ge=0.0, le=1.0, alias="resolutionConfidence"),
    ]
    retryable: bool = True
    entity_type: Annotated[
        Literal["venue", "sub_place"],
        Field(default="venue", alias="entityType"),
    ]
    authority: Literal["high", "medium", "low"] = "medium"

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def backfill_extraction_confidence(self) -> "PlaceCandidateReview":
        if self.extraction_confidence == 0.0 and self.confidence > 0.0:
            self.extraction_confidence = self.confidence
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class ExplorerContextResponse(BaseModel):
    mode: Literal["confirmed", "vague", "partial", "anchor"] = "confirmed"
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    input_completeness: Annotated[
        IntakeInputCompleteness,
        Field(
            default=IntakeInputCompleteness.complete,
            alias="inputCompleteness",
        ),
    ]
    missing_fields: Annotated[
        list[MissingFieldInfo],
        Field(default_factory=list, alias="missingFields"),
    ]
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(default_factory=list, alias="missingInfoQuestions")]
    preference_snapshot: Annotated[
        PreferenceSnapshot,
        Field(default_factory=PreferenceSnapshot, alias="preferenceSnapshot"),
    ]
    candidate_reviews: Annotated[
        list[PlaceCandidateReview],
        Field(default_factory=list, alias="candidateReviews"),
    ]
    trace: dict[str, Any] = Field(default_factory=dict)

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


class ExplorerTimingStage(BaseModel):
    key: str
    label: str
    duration_seconds: Annotated[float, Field(alias="durationSeconds")]
    details: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    model_config = {"populate_by_name": True}


class ExplorerSourceTiming(BaseModel):
    source_index: Annotated[int, Field(alias="sourceIndex")]
    platform: str
    total_seconds: Annotated[float, Field(alias="totalSeconds")]
    cache_status: Annotated[
        str,
        Field(default="unknown", alias="cacheStatus"),
    ]
    cache_lookup_seconds: Annotated[
        float,
        Field(default=0.0, alias="cacheLookupSeconds"),
    ]
    stages: list[ExplorerTimingStage] = Field(default_factory=list)
    sampled_frames: Annotated[int, Field(default=0, alias="sampledFrames")]
    speech_status: Annotated[str, Field(alias="speechStatus")]
    speech_source: Annotated[
        str,
        Field(default="none", alias="speechSource"),
    ]
    vision_status: Annotated[str, Field(alias="visionStatus")]
    stt_chunk_count: Annotated[
        int,
        Field(default=1, alias="sttChunkCount"),
    ]
    stt_audio_duration_seconds: Annotated[
        float | None,
        Field(default=None, alias="sttAudioDurationSeconds"),
    ]
    stt_chunk_duration_seconds: Annotated[
        list[float],
        Field(default_factory=list, alias="sttChunkDurationSeconds"),
    ]
    stt_chunk_retry_count: Annotated[
        int,
        Field(default=0, alias="sttChunkRetryCount"),
    ]
    extracted_place_count: Annotated[
        int,
        Field(default=0, alias="extractedPlaceCount"),
    ]
    expected_place_count: Annotated[
        int | None,
        Field(default=None, alias="expectedPlaceCount"),
    ]
    extraction_coverage: Annotated[
        float | None,
        Field(default=None, alias="extractionCoverage"),
    ]
    coverage_status: Annotated[
        str,
        Field(default="unknown", alias="coverageStatus"),
    ]
    candidate_count: Annotated[
        int,
        Field(default=0, alias="candidateCount"),
    ]
    resolved_count: Annotated[
        int,
        Field(default=0, alias="resolvedCount"),
    ]
    provider_counts: Annotated[
        dict[str, int],
        Field(default_factory=dict, alias="providerCounts"),
    ]
    resolved_provider_counts: Annotated[
        dict[str, int],
        Field(default_factory=dict, alias="resolvedProviderCounts"),
    ]

    model_config = {"populate_by_name": True}


class ExplorerProviderAttempt(BaseModel):
    candidate: str
    provider: str
    alias_query_count: Annotated[
        int,
        Field(default=0, alias="aliasQueryCount"),
    ]
    queue_wait_seconds: Annotated[
        float,
        Field(default=0.0, alias="queueWaitSeconds"),
    ]
    execution_seconds: Annotated[
        float,
        Field(default=0.0, alias="executionSeconds"),
    ]
    outcome: Literal[
        "resolved", "unresolved", "error", "timeout", "cache_hit"
    ]
    rejection_reason: Annotated[
        str | None,
        Field(default=None, alias="rejectionReason"),
    ]

    model_config = {"populate_by_name": True}


class ExplorerTimingReport(BaseModel):
    intake_id: Annotated[str, Field(alias="intakeId")]
    status: str
    total_seconds: Annotated[float, Field(alias="totalSeconds")]
    stages: list[ExplorerTimingStage] = Field(default_factory=list)
    sources: list[ExplorerSourceTiming] = Field(default_factory=list)
    url_count: Annotated[int, Field(default=0, alias="urlCount")]
    image_count: Annotated[int, Field(default=0, alias="imageCount")]
    candidate_count: Annotated[int, Field(default=0, alias="candidateCount")]
    resolved_count: Annotated[int, Field(default=0, alias="resolvedCount")]
    persisted_count: Annotated[int, Field(default=0, alias="persistedCount")]
    provider_counts: Annotated[
        dict[str, int],
        Field(default_factory=dict, alias="providerCounts"),
    ]
    resolved_provider_counts: Annotated[
        dict[str, int],
        Field(default_factory=dict, alias="resolvedProviderCounts"),
    ]
    provider_attempts: Annotated[
        list[ExplorerProviderAttempt],
        Field(default_factory=list, alias="providerAttempts"),
    ]
    log_file: Annotated[str | None, Field(default=None, alias="logFile")]

    model_config = {"populate_by_name": True}


class ExploreIntakeResponse(BaseModel):
    intake_id: Annotated[str, Field(alias="intakeId")]
    user_id: Annotated[str | None, Field(default=None, alias="userId")]
    explorer: ExplorerContextResponse
    allow_place_suggestions: Annotated[
        bool,
        Field(
            default=True,
            validation_alias=AliasChoices(
                "allowPlaceSuggestions", "allowFinderSuggestions"
            ),
            serialization_alias="allowPlaceSuggestions",
        ),
    ]
    timing_report: Annotated[
        ExplorerTimingReport | None,
        Field(default=None, alias="timingReport"),
    ]

    model_config = {"populate_by_name": True}
