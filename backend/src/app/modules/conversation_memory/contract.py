"""Contract definitions for the Conversation Memory module.

Locks domain vocabulary:
- `fact`: Structured piece of information extracted from conversation or user input.
- `reference`: Anaphoric or contextual pronoun phrase requiring entity resolution.
- `summary`: Token-efficient distillation of past turn history.
- `working_memory`: In-flight memory state bound to a single trip chat thread.
- `user_preference`: Long-term user preferences accumulated across trip chats.

External JSON uses camelCase; Python internal code uses snake_case.
"""

from datetime import datetime
from typing import Any, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class MemoryBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


FactType = Literal[
    "destination",
    "duration",
    "place_candidate",
    "travel_style",
    "budget_tier",
    "start_date",
    "note",
]

FactScope = Literal["chat", "user"]

FactStatus = Literal["active", "superseded", "expired", "rejected"]


class FactProvenance(MemoryBaseModel):
    source_turn: int = Field(ge=0, description="Message turn index")
    source_excerpt: str = Field(
        min_length=1,
        max_length=200,
        validation_alias=AliasChoices("source_excerpt", "source_text", "sourceExcerpt"),
        description="Short text excerpt (max 200 chars, no sensitive or raw third-party payload data)",
    )
    source_message_id: str | None = Field(
        default=None, max_length=120, description="Message ID in trip chat transcript"
    )
    extracted_by: str = Field(min_length=1, max_length=80, description="Extractor service name")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score in [0.0, 1.0]")

    @property
    def source_text(self) -> str:
        return self.source_excerpt


def normalize_fact_value(val: Any) -> str:
    """Normalize fact value: trim whitespace, lowercase, collapse internal whitespace."""
    if val is None:
        return ""
    if isinstance(val, str):
        import re
        return re.sub(r"\s+", " ", val.strip().lower())
    if isinstance(val, (int, float, bool)):
        return str(val)
    import json
    return json.dumps(val, sort_keys=True)


class MemoryFact(MemoryBaseModel):
    fact_id: str = Field(min_length=1, max_length=120)
    fact_type: FactType
    key: str = Field(min_length=1, max_length=100)
    value: Any = Field(description="Structured value of the fact")
    normalized_value: str | None = Field(
        default=None, description="Normalized string value for deduplication"
    )
    value_type: str = Field(
        default="string",
        min_length=1,
        max_length=32,
        description="Data type representation: string, int, float, list, dict, bool",
    )
    scope: FactScope = Field(default="chat")
    status: FactStatus = Field(default="active")
    provenance: FactProvenance
    confirmed_by_user: bool = Field(default=False)
    observed_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    created_at: datetime | None = Field(default=None)

    @property
    def computed_normalized_value(self) -> str:
        if self.normalized_value:
            return normalize_fact_value(self.normalized_value)
        return normalize_fact_value(self.value)


ReferenceType = Literal[
    "anaphora",  # "chỗ đó", "nó"
    "deictic",  # "các điểm bên trên"
    "implicit_context",  # "lịch trình vừa rồi"
]


class MemoryReference(MemoryBaseModel):
    reference_id: str = Field(min_length=1, max_length=120)
    phrase: str = Field(min_length=1, max_length=200)
    reference_type: ReferenceType
    resolved_entity: str | None = Field(default=None, max_length=300)
    target_fact_ids: list[str] = Field(default_factory=list)


class MemorySummary(MemoryBaseModel):
    summary_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=3000)
    turns_covered: int = Field(ge=1)
    key_facts_summary: list[str] = Field(default_factory=list)
    created_at: datetime | None = Field(default=None)


class WorkingMemoryState(MemoryBaseModel):
    chat_id: str = Field(min_length=1, max_length=120)
    user_id: int = Field(gt=0)
    destination: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=90)
    travelers: int | None = Field(default=None, ge=1, le=50, description="Number of travelers")
    budget: Any | None = Field(default=None, description="Budget tier or structured range")
    preferences: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)
    mentioned_places: list[str] = Field(
        default_factory=list, description="Places mentioned in transcript"
    )
    selected_places: list[str] = Field(
        default_factory=list, description="Places selected or explicitly confirmed by user"
    )
    current_plan_ref: str | None = Field(
        default=None, max_length=120, description="Reference ID to active itinerary plan"
    )
    pending_goal: str | None = Field(
        default=None, max_length=200, description="In-flight goal or unresolved intent"
    )
    last_route: str | None = Field(
        default=None, max_length=64, description="Last executed supervisor/agent route"
    )
    summary: str | None = Field(
        default=None, max_length=3000, description="Rolling context summary projection"
    )
    version: int = Field(default=0, ge=0, description="Optimistic concurrency version integer")
    active_facts: list[MemoryFact] = Field(default_factory=list)
    confirmed_facts: list[MemoryFact] = Field(default_factory=list)
    active_references: list[MemoryReference] = Field(default_factory=list)
    last_updated_at: datetime | None = Field(default=None)

    @property
    def places(self) -> list[str]:
        """Backward compatibility property returning union of mentioned and selected places."""
        combined = []
        for p in self.mentioned_places + self.selected_places:
            if p not in combined:
                combined.append(p)
        return combined


class UserPreferenceMemory(MemoryBaseModel):
    user_id: int = Field(gt=0)
    preferences: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    preferred_transport: list[str] = Field(default_factory=list)
    budget_tier: str | None = Field(default=None, max_length=50)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: FactStatus = Field(default="active")
    source_message_id: str | None = Field(default=None, max_length=120)
    updated_at: datetime | None = Field(default=None)


class RootStateMemoryMapping(MemoryBaseModel):
    """Explicit mapping schema between LangGraph RootState / TripChat and WorkingMemoryState."""

    root_request_id: str = Field(min_length=1, max_length=120)
    thread_id: str = Field(min_length=1, max_length=120)
    working_memory: WorkingMemoryState
    mapped_from_transcript_count: int = Field(ge=0)
