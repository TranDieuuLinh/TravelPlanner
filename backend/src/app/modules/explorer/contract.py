from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.shared.contracts.agent import AgentError


class ExplorerModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


def _default_start_date() -> date:
    return datetime.now().astimezone().date() + timedelta(days=1)


class ExplorerImageInput(ExplorerModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    data_base64: str | None = Field(default=None, max_length=15_000_000)
    ocr_text: str | None = Field(default=None, max_length=60_000)

    @model_validator(mode="after")
    def has_image_or_ocr(self) -> "ExplorerImageInput":
        if not (self.data_base64 or (self.ocr_text and self.ocr_text.strip())):
            raise ValueError("An image must contain dataBase64 or ocrText.")
        return self


PlaceOrigin = Literal["input", "url", "system"]
EvidenceType = Literal[
    "raw_prompt",
    "image_ocr",
    "url_metadata",
    "caption",
    "transcript",
    "stt",
    "frame_ocr",
    "web_text",
]


class PlaceSource(ExplorerModel):
    origin: PlaceOrigin
    evidence_type: EvidenceType
    source_url: str | None = Field(default=None, max_length=2048)
    evidence: str = Field(min_length=1, max_length=500)
    source_time_hint: str | None = Field(default=None, max_length=80)
    address_hint: str | None = Field(default=None, max_length=300)
    observed_at: datetime | None = None
    platform: str | None = Field(default=None, max_length=40)
    extractor_version: str | None = Field(default=None, max_length=80)
    model_version: str | None = Field(default=None, max_length=120)
    cache_status: Literal["hit", "miss", "bypassed"] | None = None


class ExplorerPlace(ExplorerModel):
    name: str = Field(min_length=1, max_length=200)
    address_hint: str | None = Field(default=None, max_length=300)
    confidence: float = Field(default=0.5, ge=0, le=1)
    source_places: list[PlaceSource] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


ItemType = Literal["food", "drink", "activity"]


class RequestedItem(ExplorerModel):
    name: str = Field(min_length=1, max_length=160)
    item_type: ItemType
    action: str = Field(min_length=1, max_length=80)
    related_place_name: str | None = Field(default=None, max_length=200)
    evidence: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class SourceNote(ExplorerModel):
    summary: str = Field(min_length=1, max_length=500)
    place_name: str | None = Field(default=None, max_length=200)
    evidence_type: EvidenceType
    source_url: str | None = Field(default=None, max_length=2048)
    observed_at: datetime | None = None


BudgetLevel = Literal["low", "medium", "high"]
BudgetSource = Literal["default", "raw_prompt", "image", "url"]
BudgetBasis = Literal["group_total", "per_person"]


class ExplorerBudget(ExplorerModel):
    level: BudgetLevel = "low"
    target_amount: int | None = Field(default=None, ge=0)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    source: BudgetSource = "default"
    basis: BudgetBasis = "group_total"

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.strip().upper()


class ExplorerPeople(ExplorerModel):
    adults: int = Field(default=1, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    infants: int = Field(default=0, ge=0, le=100)

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants


class ExplorerInput(ExplorerModel):
    raw_prompt: str | None = Field(default=None, max_length=4000)
    urls: list[str] = Field(default_factory=list, max_length=20)
    images: list[ExplorerImageInput] = Field(default_factory=list, max_length=20)
    force_refresh: bool = False

    @model_validator(mode="after")
    def has_input(self) -> "ExplorerInput":
        self.raw_prompt = (self.raw_prompt or "").strip() or None
        self.urls = list(dict.fromkeys(url.strip() for url in self.urls if url.strip()))
        if not self.raw_prompt and not self.urls and not self.images:
            raise ValueError("Provide a prompt, URL, or image.")
        return self

    @field_validator("urls")
    @classmethod
    def valid_source_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Source URLs must use http or https and include a host.")
        return values


ExplorerStatus = Literal["ready", "partial", "clarification", "error"]


class SourceCompleteness(ExplorerModel):
    source_index: int = Field(ge=0)
    source_ref: str
    coverage_status: Literal["complete", "partial", "unknown"]
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    raw_mention_count: int = Field(default=0, ge=0)
    filtered_mention_count: int = Field(default=0, ge=0)
    deduplicated_place_count: int = Field(default=0, ge=0)
    source_chunk_count: int = Field(default=0, ge=0)
    processed_source_chunk_count: int = Field(default=0, ge=0)
    synthesis_coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    discarded: dict[str, int] = Field(default_factory=dict)


class ExplorerCompleteness(ExplorerModel):
    sources: list[SourceCompleteness] = Field(default_factory=list)
    raw_mention_count: int = Field(default=0, ge=0)
    filtered_mention_count: int = Field(default=0, ge=0)
    deduplicated_place_count: int = Field(default=0, ge=0)
    discarded: dict[str, int] = Field(default_factory=dict)
    complete: bool = True


class ExplorerOutput(ExplorerModel):
    status: ExplorerStatus
    intake_id: str
    input_adm: str | None = Field(default=None, alias="input_ADM")
    places: list[ExplorerPlace] | None = None
    input_items: list[RequestedItem] | None = None
    url_notes: list[SourceNote] | None = None
    days: int = Field(default=3, ge=1, le=30)
    start_date: date = Field(default_factory=_default_start_date)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=100)
    budget: ExplorerBudget = Field(default_factory=ExplorerBudget)
    people: ExplorerPeople = Field(default_factory=ExplorerPeople)
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)
    clarification_question: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list)
    completeness: ExplorerCompleteness | None = None
    error: AgentError | None = None
