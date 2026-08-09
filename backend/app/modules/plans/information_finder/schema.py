from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class InformationSource(StrEnum):
    """Allowed sources for a Finder query or candidate."""

    knowledge_graph = "knowledge_graph"
    explorer_import = "explorer_import"
    external_provider = "external_provider"


class InformationQuery(_ContractModel):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    source_kinds: Annotated[
        list[InformationSource],
        Field(default_factory=lambda: list(InformationSource), alias="sourceKinds"),
    ]
    top_k: Annotated[int, Field(default=5, ge=1, le=10, alias="topK")]
    destination: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_a_source(self) -> "InformationQuery":
        if not self.source_kinds:
            raise ValueError("sourceKinds must contain at least one source")
        return self


class InformationAnswer(_ContractModel):
    """LLM-authored answer returned by the InformationFinder agent."""

    answer: Annotated[str, Field(min_length=1, max_length=4000)]


class InformationCandidate(_ContractModel):
    candidate_id: Annotated[str, Field(min_length=1, max_length=128, alias="candidateId")]
    place_id: Annotated[
        str | None,
        Field(default=None, min_length=1, max_length=128, alias="placeId"),
    ]
    source: InformationSource
    source_refs: Annotated[
        list[str],
        Field(min_length=1, max_length=32, alias="sourceRefs"),
    ]
    source_import_node_id: Annotated[
        int | None,
        Field(default=None, ge=1, alias="sourceImportNodeId"),
    ]
    candidate_entity_ids: Annotated[
        list[str],
        Field(default_factory=list, max_length=32, alias="candidateEntityIds"),
    ]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    confidence: Annotated[float, Field(ge=0, le=1)]
    is_verified: Annotated[bool, Field(default=False, alias="isVerified")]
    fetched_at: Annotated[datetime, Field(alias="fetchedAt")]
    display_name: str | None = Field(
        default=None, min_length=1, max_length=255, alias="displayName"
    )
    address: str | None = Field(default=None, min_length=1, max_length=500)
    distance_to_center_km: float | None = Field(
        default=None, ge=0, alias="distanceToCenterKm"
    )
    max_origin_distance_km: float | None = Field(
        default=None, ge=0, alias="maxOriginDistanceKm"
    )

    @model_validator(mode="after")
    def validate_identity_and_coordinates(self) -> "InformationCandidate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if not (self.place_id or self.source_import_node_id or self.candidate_entity_ids):
            raise ValueError(
                "candidate must have placeId, sourceImportNodeId, or candidateEntityIds"
            )
        if self.is_verified and (self.place_id is None or self.latitude is None):
            raise ValueError("verified candidates require placeId and coordinates")
        return self


class InformationResult(_ContractModel):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    candidates: list[InformationCandidate] = Field(default_factory=list, max_length=10)
    needs_user_choice: Annotated[bool, Field(default=False, alias="needsUserChoice")]
    warnings: list[str] = Field(default_factory=list, max_length=50)
    meeting_point: dict[str, float] | None = Field(
        default=None, alias="meetingPoint"
    )
    resolved_origins: list[dict[str, object]] = Field(
        default_factory=list, max_length=8, alias="resolvedOrigins"
    )
