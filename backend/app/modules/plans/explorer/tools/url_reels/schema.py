from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.plans.dto.agent_contracts import ItineraryItemCategory


class UrlReelInput(BaseModel):
    url: str
    destination: str | None = None
    work_dir: Path | None = Field(default=None, alias="workDir")
    stt_language: str | None = Field(default="en,vi", alias="sttLanguage")
    stt_initial_prompt: str | None = Field(default=None, alias="sttInitialPrompt")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class UrlMetadata(BaseModel):
    original_url: str = Field(alias="originalUrl")
    canonical_url: str = Field(alias="canonicalUrl")
    platform: str
    title: str | None = None
    description: str | None = None
    duration_seconds: int | None = Field(default=None, alias="durationSeconds")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    uploader: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class MediaArtifacts(BaseModel):
    video_path: Path | None = Field(default=None, alias="videoPath")
    audio_path: Path | None = Field(default=None, alias="audioPath")
    frame_paths: list[Path] = Field(default_factory=list, alias="framePaths")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class SpeechToTextObservation(BaseModel):
    order: int = Field(ge=1)
    place_name: str = Field(alias="placeName")
    evidence: str
    day_number: int | None = Field(default=None, ge=1, le=30, alias="dayNumber")
    time_hint: str = Field(default="", alias="timeHint")
    activity: str = ""
    search_region: str = Field(default="", alias="searchRegion")
    duration_minutes: int | None = Field(
        default=None,
        ge=15,
        le=720,
        alias="durationMinutes",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    entity_type: Literal[
        "venue",
        "sub_place",
        "address",
        "city",
        "person",
        "activity",
        "food",
        "unknown",
    ] = Field(default="venue", alias="entityType")
    aliases: list[str] = Field(default_factory=list)
    address_hint: str | None = Field(default=None, alias="addressHint")
    parent_place: str | None = Field(default=None, alias="parentPlace")
    evidence_source: Literal["metadata", "caption", "stt"] = Field(
        default="stt",
        alias="evidenceSource",
    )
    authority: Literal["high", "medium", "low"] = "medium"

    model_config = {"populate_by_name": True, "extra": "forbid"}


class SpeechToTextResult(BaseModel):
    text: str
    observations: list[SpeechToTextObservation] = Field(default_factory=list)
    region_story: str = Field(default="", alias="regionStory")
    region_story_evidence: str = Field(default="", alias="regionStoryEvidence")
    status: str = "ok"
    source: str = "none"
    error: str | None = None
    language: str | None = None
    language_probability: float | None = Field(default=None, alias="languageProbability")
    duration_seconds: float = Field(alias="durationSeconds")
    audio_duration_seconds: float | None = Field(
        default=None,
        alias="audioDurationSeconds",
    )
    chunk_count: int = Field(default=1, ge=1, alias="chunkCount")
    chunk_duration_seconds: list[float] = Field(
        default_factory=list,
        alias="chunkDurationSeconds",
    )
    chunk_retry_count: int = Field(
        default=0,
        ge=0,
        alias="chunkRetryCount",
    )

    model_config = {"populate_by_name": True}


class FrameVisionObservation(BaseModel):
    order: int | None = Field(default=None, ge=1)
    place_name: str = Field(alias="placeName")
    evidence: str = ""
    day_number: int | None = Field(default=None, ge=1, le=30, alias="dayNumber")
    time_hint: str | None = Field(default=None, alias="timeHint")
    activity: str | None = None
    entity_type: Literal[
        "venue", "sub_place", "address", "city", "person", "unknown"
    ] = Field(default="venue", alias="entityType")
    address_hint: str | None = Field(default=None, alias="addressHint")
    parent_place: str | None = Field(default=None, alias="parentPlace")

    model_config = {"populate_by_name": True}


class FrameVisionResult(BaseModel):
    text: str = ""
    places: list[str] = Field(default_factory=list)
    observations: list[FrameVisionObservation] = Field(default_factory=list)
    status: str = "skipped"
    error: str | None = None
    duration_seconds: float = Field(default=0.0, alias="durationSeconds")

    model_config = {"populate_by_name": True}


class ExtractedPlace(BaseModel):
    name: str
    category: ItineraryItemCategory = ItineraryItemCategory.other
    address: str | None = None
    search_region: str | None = Field(default=None, alias="searchRegion")
    source: str = "url_reel"
    evidence: str | None = None
    source_evidence: dict[str, str] = Field(
        default_factory=dict,
        alias="sourceEvidence",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    attributes: list[str] = Field(default_factory=list)
    source_order: int | None = Field(default=None, ge=1, alias="sourceOrder")
    source_day: int | None = Field(default=None, ge=1, le=30, alias="sourceDay")
    source_time_hint: str | None = Field(default=None, alias="sourceTimeHint")
    source_activity: str | None = Field(default=None, alias="sourceActivity")
    source_duration_minutes: int | None = Field(
        default=None,
        ge=15,
        le=720,
        alias="sourceDurationMinutes",
    )
    entity_type: Literal["venue", "sub_place"] = Field(
        default="venue",
        alias="entityType",
    )
    aliases: list[str] = Field(default_factory=list)
    parent_place: str | None = Field(default=None, alias="parentPlace")
    authority: Literal["high", "medium", "low"] = "medium"

    model_config = {"populate_by_name": True}


class ExtractedDestinationStay(BaseModel):
    """A city/region heading that allocates days but is not a visitable stop."""

    name: str = Field(min_length=1)
    duration_days: int = Field(ge=1, le=30, alias="durationDays")
    start_day: int = Field(ge=1, le=30, alias="startDay")
    end_day: int = Field(ge=1, le=30, alias="endDay")
    source_order: int | None = Field(default=None, ge=1, alias="sourceOrder")
    evidence: str | None = None

    model_config = {"populate_by_name": True}


class RegionSourceStory(BaseModel):
    """Destination-level creator context with an exact supporting source span."""

    text: str = Field(min_length=1, max_length=360)
    evidence: str = Field(min_length=1, max_length=500)
    evidence_type: Literal["caption", "stt"] = Field(alias="evidenceType")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class ExtractedContext(BaseModel):
    extracted_places: list[str] = Field(default_factory=list, alias="extractedPlaces")
    extracted_place_details: list[ExtractedPlace] = Field(default_factory=list, alias="extractedPlaceDetails")
    destination_stays: list[ExtractedDestinationStay] = Field(
        default_factory=list,
        alias="destinationStays",
    )
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)
    region_story: RegionSourceStory | None = Field(
        default=None,
        alias="regionStory",
    )
    expected_place_count: int | None = Field(
        default=None,
        ge=1,
        le=100,
        alias="expectedPlaceCount",
    )
    extraction_coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        alias="extractionCoverage",
    )
    coverage_status: Literal["unknown", "sufficient", "review", "insufficient"] = Field(
        default="unknown",
        alias="coverageStatus",
    )

    model_config = {"populate_by_name": True}


class UrlReelExtractionResult(BaseModel):
    url: str
    platform: str
    metadata: UrlMetadata
    artifacts: MediaArtifacts
    needs_image_upload: bool = Field(default=False, alias="needsImageUpload")
    speech_to_text: SpeechToTextResult = Field(alias="speechToText")
    frame_vision: FrameVisionResult = Field(
        default_factory=FrameVisionResult,
        alias="frameVision",
    )
    extracted_context: ExtractedContext = Field(alias="extractedContext")
    timings: dict[str, float]

    model_config = {"populate_by_name": True}
