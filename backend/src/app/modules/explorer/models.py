from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerPeople,
    ExplorerPlace,
    RequestedItem,
    SourceNote,
)
from app.shared.contracts.agent import AgentError


class InternalModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AdmEvidence(InternalModel):
    value: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=80)
    source_url: str | None = Field(default=None, max_length=2048)
    confidence: float = Field(default=0.5, ge=0, le=1)


class BudgetSignal(InternalModel):
    budget: ExplorerBudget
    confidence: float = Field(default=0.5, ge=0, le=1)


ArtifactType = Literal[
    "url_metadata",
    "caption",
    "transcript",
    "stt",
    "frame_ocr",
    "web_text",
    "image_ocr",
]


class SourceArtifact(InternalModel):
    artifact_type: ArtifactType
    text: str = Field(min_length=1, max_length=60_000)
    source_url: str | None = Field(default=None, max_length=2048)
    source_time_hint: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=20)
    observed_at: str | None = None


SourceBranch = Literal["frame_ocr", "stt"]


class SourceBranchFailure(InternalModel):
    branch: SourceBranch
    error: AgentError


class MediaAnalysisResult(InternalModel):
    artifacts: list[SourceArtifact] = Field(default_factory=list)
    failures: list[SourceBranchFailure] = Field(default_factory=list)


SourceStatus = Literal[
    "succeeded",
    "partial",
    "failed_retryable",
    "failed_permanent",
]
CacheStatus = Literal["hit", "miss", "bypassed"]


class SourceExtractionResult(InternalModel):
    source_index: int = Field(ge=0)
    source_kind: Literal["url", "image"]
    source_ref: str = Field(min_length=1, max_length=2048)
    status: SourceStatus
    adm_candidates: list[AdmEvidence] = Field(default_factory=list)
    places: list[ExplorerPlace] = Field(default_factory=list)
    notes: list[SourceNote] = Field(default_factory=list)
    budget_signals: list[BudgetSignal] = Field(default_factory=list)
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)
    expected_place_count: int | None = Field(default=None, ge=0)
    extracted_place_count: int = Field(default=0, ge=0)
    error: AgentError | None = None
    artifacts: list[SourceArtifact] = Field(default_factory=list)
    branch_failures: list[SourceBranchFailure] = Field(default_factory=list)
    cache_status: CacheStatus | None = None


class ExplorerDraft(InternalModel):
    input_adm: str | None = None
    adm_candidates: list[AdmEvidence] = Field(default_factory=list)
    places: list[ExplorerPlace] = Field(default_factory=list)
    input_items: list[RequestedItem] = Field(default_factory=list)
    url_notes: list[SourceNote] = Field(default_factory=list)
    budget: ExplorerBudget = Field(default_factory=ExplorerBudget)
    people: ExplorerPeople = Field(default_factory=ExplorerPeople)
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)


BatchCoverage = Literal["usable", "partial", "fatal"]
