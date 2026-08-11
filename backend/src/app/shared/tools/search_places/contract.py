from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.contracts.place import Coordinates


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ToolModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )


class AdministrativeArea(ToolModel):
    adm_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    level: str = Field(default="ADM1", min_length=1, max_length=32)
    country_code: str = Field(min_length=2, max_length=3)

    @field_validator("adm_id", "name", "level", "country_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str) -> str:
        return value.upper()


SearchMode = Literal["named_place", "requirement"]
SearchStatus = Literal[
    "resolved",
    "needs_review",
    "unresolved",
    "provider_error",
]


class PlaceSearchRequest(ToolModel):
    query: str = Field(min_length=1, max_length=200)
    input_adm: AdministrativeArea
    search_mode: SearchMode = "named_place"
    alternate_names: list[str] = Field(default_factory=list, max_length=2)
    address_hint: str | None = Field(default=None, max_length=300)
    place_type_hint: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=2048)
    source_evidence: str | None = Field(default=None, max_length=500)
    source_time_hint: str | None = Field(default=None, max_length=80)
    previous_place: Coordinates | None = None
    next_place: Coordinates | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    allow_external_fallback: bool = True

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        return value.strip()

    @field_validator("alternate_names")
    @classmethod
    def normalize_alternate_names(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                result.append(cleaned)
                seen.add(key)
        return result[:2]


class PlaceProviderCandidate(ToolModel):
    provider: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    entity_id: str | None = Field(default=None, max_length=200)
    provider_id: str | None = Field(default=None, max_length=300)
    aliases: list[str] = Field(default_factory=list)
    address: str | None = Field(default=None, max_length=500)
    coordinates: Coordinates | None = None
    adm_ids: list[str] = Field(default_factory=list)
    adm_names: list[str] = Field(default_factory=list)
    canonical_type: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list)
    data_confidence: float = Field(default=0.5, ge=0, le=1)
    fetched_at: datetime | None = None

    @property
    def stable_id(self) -> str | None:
        return self.entity_id or self.provider_id


class PlaceSearchMatch(ToolModel):
    place_id: str | None = None
    provider: str
    provider_id: str | None = None
    name: str
    canonical_type: str | None = None
    address: str | None = None
    coordinates: Coordinates | None = None
    tags: list[str] = Field(default_factory=list)
    score: float = Field(ge=0, le=1)
    score_components: dict[str, float] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None


class ProviderAttempt(ToolModel):
    provider: str
    outcome: Literal["resolved", "candidates", "empty", "error", "timeout"]
    queries: list[str] = Field(default_factory=list)
    candidate_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    error_code: str | None = None


class PlaceSearchResult(ToolModel):
    status: SearchStatus
    query: str
    normalized_query: str
    search_mode: SearchMode
    selected: PlaceSearchMatch | None = None
    top_matches: list[PlaceSearchMatch] = Field(default_factory=list)
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)
    resolution_reason: str
    retryable: bool = False

