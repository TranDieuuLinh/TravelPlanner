from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class PreferenceDimension(StrEnum):
    category = "category"
    attribute = "attribute"
    cuisine = "cuisine"
    budget = "budget"
    pace = "pace"
    time_of_day = "time_of_day"
    transport = "transport"
    setting = "setting"


class PreferenceSignal(BaseModel):
    dimension: PreferenceDimension
    value: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: str = Field(default="trip", pattern=r"^(trip|destination|global)$")
    destination: str | None = None
    origin: Literal["explicit", "inferred"] = "inferred"
    source_types: Annotated[
        list[str],
        Field(default_factory=list, alias="sourceTypes"),
    ]

    model_config = {"populate_by_name": True}

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return value.strip().casefold().replace("-", "_").replace(" ", "_")

    @property
    def key(self) -> str:
        return f"{self.dimension.value}:{self.value}"


class PreferenceAggregate(BaseModel):
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    observations: int = Field(default=1, ge=1)
    origin: Literal["explicit", "inferred"] = "inferred"
    source_types: Annotated[
        list[str],
        Field(default_factory=list, alias="sourceTypes"),
    ]
    last_observed_at: Annotated[
        datetime | None,
        Field(default=None, alias="lastObservedAt"),
    ]

    model_config = {"populate_by_name": True}


class LongTermPreferenceProfile(BaseModel):
    version: int = 1
    explicit: list[str] = Field(default_factory=list)
    scores: dict[str, PreferenceAggregate] = Field(default_factory=dict)
    observation_count: Annotated[int, Field(default=0, ge=0, alias="observationCount")]
    updated_at: Annotated[
        datetime | None,
        Field(default=None, alias="updatedAt"),
    ]

    model_config = {"populate_by_name": True}

    @classmethod
    def from_storage(
        cls,
        value: object,
    ) -> "LongTermPreferenceProfile":
        if isinstance(value, cls):
            return value.model_copy(deep=True)
        if isinstance(value, list):
            explicit = [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]
            return cls(explicit=list(dict.fromkeys(explicit)))
        if isinstance(value, dict):
            return cls.model_validate(value)
        return cls()

    def top_values(
        self,
        *,
        dimensions: set[PreferenceDimension] | None = None,
        minimum_score: float = 0.2,
        limit: int = 12,
    ) -> list[str]:
        ranked: list[tuple[float, str]] = []
        for key, aggregate in self.scores.items():
            dimension_value, _, value = key.partition(":")
            if not value:
                continue
            try:
                dimension = PreferenceDimension(dimension_value)
            except ValueError:
                continue
            if dimensions is not None and dimension not in dimensions:
                continue
            if aggregate.score < minimum_score:
                continue
            if aggregate.origin == "inferred" and aggregate.observations < 2:
                continue
            ranked.append(
                (
                    aggregate.score * aggregate.confidence,
                    value,
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return list(dict.fromkeys([*self.explicit, *(value for _, value in ranked)]))[
            :limit
        ]


class PreferenceSnapshot(BaseModel):
    version: int = 1
    signals: list[PreferenceSignal] = Field(default_factory=list)
    effective_profile: Annotated[
        LongTermPreferenceProfile,
        Field(default_factory=LongTermPreferenceProfile, alias="effectiveProfile"),
    ]

    model_config = {"populate_by_name": True}


class TravelerPreferenceSignalRead(BaseModel):
    id: str
    dimension: str
    value: str
    label: str
    score: float
    confidence: float
    observations: int
    scope: str
    destination: str | None = None
    origin: str
    status: str
    source_types: Annotated[list[str], Field(alias="sourceTypes")]
    first_observed_at: Annotated[datetime, Field(alias="firstObservedAt")]
    last_observed_at: Annotated[datetime, Field(alias="lastObservedAt")]
    last_evidence_intake_id: Annotated[
        str | None, Field(alias="lastEvidenceIntakeId")
    ] = None

    model_config = {"populate_by_name": True}


class TravelerProfileRead(BaseModel):
    user_id: Annotated[int, Field(alias="userId")]
    explicit_preferences: Annotated[
        list[str], Field(alias="explicitPreferences")
    ]
    top_preferences: Annotated[list[str], Field(alias="topPreferences")]
    observation_count: Annotated[int, Field(alias="observationCount")]
    signals: list[TravelerPreferenceSignalRead]
    updated_at: Annotated[datetime | None, Field(alias="updatedAt")]

    model_config = {"populate_by_name": True}


class TravelerProfileUpdate(BaseModel):
    explicit_preferences: Annotated[
        list[str], Field(max_length=20, alias="explicitPreferences")
    ]

    model_config = {"populate_by_name": True}

    @field_validator("explicit_preferences")
    @classmethod
    def normalize_explicit_preferences(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if any(len(item) > 80 for item in normalized):
            raise ValueError("Each preference must be at most 80 characters")
        return list(dict.fromkeys(normalized))
