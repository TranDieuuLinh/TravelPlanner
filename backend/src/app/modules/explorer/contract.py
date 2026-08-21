from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.shared.contracts.agent import AgentError
from app.modules.explorer.place_keys import place_name_key
from app.modules.explorer.review_types import ExplorerDefaultedField
from app.modules.explorer.trip_defaults import tomorrow


class ExplorerModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


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
    adults: int = Field(default=2, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    infants: int = Field(default=0, ge=0, le=100)

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants


class ExplorerInput(ExplorerModel):
    # Optional compatibility field for direct Explorer callers; orchestration
    # no longer forwards the current user message as rawPrompt.
    raw_prompt: str | None = Field(default=None, max_length=4000)
    urls: list[str] = Field(default_factory=list, max_length=20)
    images: list[ExplorerImageInput] = Field(default_factory=list, max_length=20)
    force_refresh: bool = False
    conversation_context: list[str] = Field(default_factory=list, max_length=6)
    conversation_summary: str | None = Field(default=None, max_length=2000)
    explorer_output: dict | None = None
    resolved_entities: list[str] = Field(default_factory=list, max_length=30)
    destination: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=60)
    mentioned_places: list[str] = Field(default_factory=list, max_length=50)
    selected_places: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def has_input(self) -> "ExplorerInput":
        self.raw_prompt = (self.raw_prompt or "").strip() or None
        self.urls = list(dict.fromkeys(url.strip() for url in self.urls if url.strip()))
        self.conversation_context = [item.strip() for item in self.conversation_context if item.strip()]
        self.conversation_summary = (self.conversation_summary or "").strip() or None
        self.resolved_entities = [item.strip() for item in self.resolved_entities if item.strip()]
        if self.explorer_output is not None and not isinstance(self.explorer_output, dict):
            raise ValueError("explorer_output must be an object.")
        self.destination = (self.destination or "").strip() or None
        self.mentioned_places = [item.strip() for item in self.mentioned_places if item.strip()]
        self.selected_places = [item.strip() for item in self.selected_places if item.strip()]
        if not (
            self.urls
            or self.images
            or self.raw_prompt
            or self.conversation_context
            or self.conversation_summary
            or self.destination
            or self.duration_days
            or self.mentioned_places
            or self.selected_places
        ):
            raise ValueError("Provide context, URL, or image.")
        return self

    @field_validator("urls")
    @classmethod
    def valid_source_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    "Source URLs must use http or https and include a host."
                )
        return values


ExplorerStatus = Literal["ready", "partial", "clarification", "error"]


class ExplorerOutput(ExplorerModel):
    status: ExplorerStatus
    intake_id: str
    input_adm: str | None = Field(default=None, alias="input_ADM")
    places: list[ExplorerPlace] | None = None
    input_items: list[RequestedItem] | None = None
    url_notes: list[SourceNote] | None = None
    days: int = Field(default=3, ge=1, le=30)
    start_date: date = Field(default_factory=tomorrow)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=100)
    budget: ExplorerBudget = Field(default_factory=ExplorerBudget)
    people: ExplorerPeople = Field(default_factory=ExplorerPeople)
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)
    preference_inputs: list[str] = Field(default_factory=list)
    avoid_inputs: list[str] = Field(default_factory=list)
    special_notes: list[str] = Field(default_factory=list, max_length=50)
    clarification_question: str | None = Field(default=None, max_length=500)
    defaulted_fields: list[ExplorerDefaultedField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: AgentError | None = None


PublicEvidenceType = Literal["raw_prompt", "url"]


def _public_evidence_type(*, is_url: bool) -> PublicEvidenceType:
    return "url" if is_url else "raw_prompt"


class ExplorerApiSourceNote(ExplorerModel):
    summary: str

    @classmethod
    def from_internal(cls, note: SourceNote) -> "ExplorerApiSourceNote":
        return cls(summary=note.summary)


class ExplorerApiPlaceSource(ExplorerModel):
    evidence_type: PublicEvidenceType
    source_url: str | None = Field(default=None, max_length=2048)
    source_time_hint: str | None = Field(default=None, max_length=80)
    address_hint: str | None = Field(default=None, max_length=300)
    url_notes: list[ExplorerApiSourceNote]

    @classmethod
    def from_internal(
        cls, source: PlaceSource, *, notes: list[SourceNote]
    ) -> "ExplorerApiPlaceSource":
        return cls(
            evidence_type=_public_evidence_type(is_url=source.origin == "url"),
            source_url=source.source_url,
            source_time_hint=source.source_time_hint,
            address_hint=source.address_hint,
            url_notes=[ExplorerApiSourceNote.from_internal(note) for note in notes],
        )


class ExplorerApiRequestedItem(ExplorerModel):
    name: str
    item_type: ItemType
    related_place_name: str | None = None


class ExplorerApiPlace(ExplorerModel):
    name: str
    source_places: list[ExplorerApiPlaceSource]

    @classmethod
    def from_internal(
        cls,
        place: ExplorerPlace,
        *,
        notes: list[SourceNote],
    ) -> "ExplorerApiPlace":
        return cls(
            name=place.name,
            source_places=cls._unique_sources(place.source_places, notes),
        )

    @classmethod
    def _unique_sources(
        cls, sources: list[PlaceSource], notes: list[SourceNote]
    ) -> list[ExplorerApiPlaceSource]:
        unique: list[ExplorerApiPlaceSource] = []
        by_signature: dict[
            tuple[str, str | None, str | None, str | None],
            ExplorerApiPlaceSource,
        ] = {}
        seen: set[tuple[str, str | None, str | None, str | None]] = set()
        for source in sources:
            public = ExplorerApiPlaceSource.from_internal(
                source, notes=cls._notes_for_source(source, notes)
            )
            signature = (
                public.evidence_type,
                public.source_url,
                public.source_time_hint,
                public.address_hint,
            )
            if signature not in seen:
                unique.append(public)
                seen.add(signature)
                by_signature[signature] = public
            else:
                stored = by_signature[signature]
                stored.url_notes = cls._unique_notes(
                    [*stored.url_notes, *public.url_notes]
                )
        return unique

    @staticmethod
    def _notes_for_source(
        source: PlaceSource, notes: list[SourceNote]
    ) -> list[SourceNote]:
        source_is_url = source.origin == "url"
        return [
            note
            for note in notes
            if (note.source_url is not None) == source_is_url
            and (not source_is_url or note.source_url == source.source_url)
        ]

    @staticmethod
    def _unique_notes(
        notes: list[ExplorerApiSourceNote],
    ) -> list[ExplorerApiSourceNote]:
        return list({note.summary: note for note in notes}.values())


class ExplorerApiBudget(ExplorerModel):
    amount_per_person: int | None = None
    currency: str
    level: BudgetLevel


class ExplorerApiOutput(ExplorerModel):
    intake_id: str
    input_adm: str | None = Field(default=None, alias="input_ADM")
    places: list[ExplorerApiPlace] | None = None
    input_items: list[ExplorerApiRequestedItem] | None = None
    days: int
    start_date: date
    timezone: str
    budget: ExplorerApiBudget
    people: ExplorerPeople
    short_preferences: list[str]
    short_avoids: list[str]
    special_notes: list[str]

    @classmethod
    def from_internal(
        cls,
        output: ExplorerOutput,
        *,
        filter_tags: Callable[[list[str]], list[str]],
    ) -> "ExplorerApiOutput":
        notes = output.url_notes or []
        return cls(
            intake_id=output.intake_id,
            input_adm=output.input_adm,
            places=(
                [
                    ExplorerApiPlace.from_internal(
                        place,
                        notes=cls._notes_for_place(place, notes),
                    )
                    for place in output.places
                ]
                if output.places is not None
                else None
            ),
            input_items=(
                [
                    ExplorerApiRequestedItem(
                        name=item.name,
                        item_type=item.item_type,
                        related_place_name=item.related_place_name,
                    )
                    for item in output.input_items
                ]
                if output.input_items is not None
                else None
            ),
            days=output.days,
            start_date=output.start_date,
            timezone=output.timezone,
            budget=ExplorerApiBudget(
                amount_per_person=cls._amount_per_person(output),
                currency=output.budget.currency,
                level=output.budget.level,
            ),
            people=output.people,
            short_preferences=filter_tags(output.short_preferences),
            short_avoids=filter_tags(output.short_avoids),
            special_notes=output.special_notes,
        )

    @staticmethod
    def _amount_per_person(output: ExplorerOutput) -> int | None:
        amount = output.budget.target_amount
        if amount is None or output.budget.basis == "per_person":
            return amount
        return int(
            (Decimal(amount) / Decimal(output.people.total)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    @staticmethod
    def _notes_for_place(
        place: ExplorerPlace, notes: list[SourceNote]
    ) -> list[SourceNote]:
        place_key = place_name_key(place.name)
        matched: list[SourceNote] = []
        seen: set[tuple[str, str | None]] = set()
        for note in notes:
            note_place = place_name_key(note.place_name or "")
            summary = place_name_key(note.summary)
            if note_place != place_key and place_key not in summary:
                continue
            signature = (summary, note.source_url)
            if signature not in seen:
                matched.append(note)
                seen.add(signature)
        return matched
