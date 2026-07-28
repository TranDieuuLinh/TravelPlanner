from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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


class SpeechToTextResult(BaseModel):
    text: str
    status: str = "ok"
    error: str | None = None
    language: str | None = None
    language_probability: float | None = Field(default=None, alias="languageProbability")
    duration_seconds: float = Field(alias="durationSeconds")

    model_config = {"populate_by_name": True}


class ExtractedPlace(BaseModel):
    name: str
    address: str | None = None
    source: str = "url_reel"
    evidence: str | None = None

    model_config = {"populate_by_name": True}


class ExtractedContext(BaseModel):
    extracted_places: list[str] = Field(default_factory=list, alias="extractedPlaces")
    extracted_place_details: list[ExtractedPlace] = Field(default_factory=list, alias="extractedPlaceDetails")
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UrlReelExtractionResult(BaseModel):
    url: str
    platform: str
    metadata: UrlMetadata
    artifacts: MediaArtifacts
    needs_image_upload: bool = Field(default=False, alias="needsImageUpload")
    speech_to_text: SpeechToTextResult = Field(alias="speechToText")
    extracted_context: ExtractedContext = Field(alias="extractedContext")
    timings: dict[str, float]

    model_config = {"populate_by_name": True}
