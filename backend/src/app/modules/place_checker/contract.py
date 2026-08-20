from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from app.modules.place_checker.enums import (
    AdmResolutionStatus,
    BudgetMode,
    EvidenceOrigin,
    IssueSeverity,
    SourceTier,
    TravelPace,
)
from app.modules.place_checker.compat_output_contract import PlaceCheckerOutput as PlaceCheckerOutput
from app.modules.place_checker.handoff_adapter import (
    expand_compact_budget,
    expand_compact_item,
    expand_compact_place,
    serialize_compact_handoff,
)
from app.shared.contracts.place import Coordinates, PlaceCandidate
from app.shared.contracts.trip import TripIntent

def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class SourcePlaceEvidence(ContractModel):
    origin: EvidenceOrigin
    evidence_type: str = Field(min_length=1, max_length=80)
    source_url: str | None = Field(default=None, max_length=2048)
    evidence: str = Field(min_length=1, max_length=4000)
    source_time_hint: str | None = Field(default=None, max_length=120)
    address_hint: str | None = Field(default=None, max_length=500)
    observed_at: datetime | None = None
    platform: str | None = Field(default=None, max_length=40)
    extractor_version: str | None = Field(default=None, max_length=80)
    model_version: str | None = Field(default=None, max_length=120)
    cache_status: Literal["hit", "miss", "bypassed"] | None = None


class PlaceCandidateInput(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    address_hint: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)
    source_places: list[SourcePlaceEvidence] = Field(min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> PlaceCandidateInput:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self

    @property
    def source_tier(self) -> SourceTier:
        origins = {source.origin for source in self.source_places}
        if EvidenceOrigin.input in origins:
            return SourceTier.direct_user
        if EvidenceOrigin.url in origins:
            return SourceTier.url
        return SourceTier.system_suggested


class InputItem(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    item_type: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=80)
    related_place_name: str | None = Field(default=None, max_length=200)
    evidence: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)


class UrlNote(ContractModel):
    summary: str = Field(min_length=1, max_length=2000)
    place_name: str | None = Field(default=None, max_length=200)
    evidence_type: str = Field(min_length=1, max_length=80)
    source_url: str | None = Field(default=None, max_length=2000)
    observed_at: datetime | None = None


class BudgetInput(ContractModel):
    level: Literal["low", "medium", "high"]
    target_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    source: str = Field(min_length=1, max_length=80)
    basis: Literal["group_total", "per_person"] = "per_person"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def target_requires_currency(self) -> "BudgetInput":
        if self.target_amount is not None and self.currency is None:
            raise ValueError("currency is required when target_amount is provided")
        return self

    @property
    def amount_per_person(self) -> Decimal | None:
        return self.target_amount


class PeopleInput(ContractModel):
    adults: int = Field(ge=0, le=100)
    children: int = Field(ge=0, le=100)
    infants: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def group_size_is_supported(self) -> PeopleInput:
        if self.total < 1:
            raise ValueError("at least one traveler is required")
        if self.total > 100:
            raise ValueError("at most 100 travelers are supported")
        return self

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants


class CandidateValidationIssue(ContractModel):
    index: int = Field(ge=0)
    name: str | None = None
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.high


class AdmResolution(ContractModel):
    input_name: str = Field(min_length=1, max_length=120)
    status: AdmResolutionStatus
    adm_id: str | None = None
    canonical_name: str | None = None
    country_code: str | None = None
    region_key: str | None = None
    alternatives: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def resolved_adm_is_complete(self) -> AdmResolution:
        required = (
            self.adm_id,
            self.canonical_name,
            self.country_code,
            self.region_key,
        )
        if self.status == AdmResolutionStatus.resolved and not all(required):
            raise ValueError("resolved ADM requires identity, country, and region")
        return self


class CapacityRange(ContractModel):
    minimum_minutes: int = Field(ge=0)
    typical_minutes: int = Field(ge=0)
    maximum_minutes: int = Field(ge=0)

    @model_validator(mode="after")
    def values_are_ordered(self) -> CapacityRange:
        if not (self.minimum_minutes <= self.typical_minutes <= self.maximum_minutes):
            raise ValueError("capacity values must be ordered")
        return self


class TripEvaluationContext(ContractModel):
    destination: AdmResolution
    days: int = Field(ge=1, le=30)
    pace: TravelPace = TravelPace.balanced
    capacity: CapacityRange
    budget_mode: BudgetMode
    budget: BudgetInput
    people: PeopleInput
    preferences: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)


class PlaceCheckerInput(ContractModel):
    input_adm: str = Field(
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("inputADM", "input_ADM", "input_adm"),
        serialization_alias="inputADM",
    )
    places: list[PlaceCandidateInput] = Field(default_factory=list, max_length=100)
    input_items: list[InputItem] = Field(default_factory=list, max_length=50)
    url_notes: list[UrlNote] = Field(default_factory=list, max_length=200, exclude=True)
    days: int = Field(ge=1, le=30)
    budget: BudgetInput
    people: PeopleInput
    short_preferences: list[str] = Field(default_factory=list)
    short_avoids: list[str] = Field(default_factory=list)
    special_notes: list[str] = Field(default_factory=list, max_length=50)
    validation_issues: list[CandidateValidationIssue] = Field(
        default_factory=list,
        exclude=True,
    )

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def adapt_and_collect_candidate_issues(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if (
            not {"inputADM", "input_ADM", "input_adm"}.intersection(data)
            and "intent" in data
        ):
            data = cls._adapt_legacy_payload(data)

        for alias, field_name in (
            ("inputItems", "input_items"),
            ("urlNotes", "url_notes"),
            ("shortPreferences", "short_preferences"),
            ("shortAvoids", "short_avoids"),
            ("specialNotes", "special_notes"),
        ):
            if field_name not in data and alias in data:
                data[field_name] = data.pop(alias)

        # The compatibility graph receives Explorer Pydantic objects, while
        # the rich pipeline normally receives plain JSON dictionaries.
        # Convert both shapes before candidate-level validation.
        for field_name in ("places", "input_items", "url_notes"):
            values = data.get(field_name)
            if values is None:
                data[field_name] = []
                continue
            if isinstance(values, list):
                data[field_name] = [
                    value.model_dump() if isinstance(value, BaseModel) else value
                    for value in values
                ]
        for field_name in ("budget", "people"):
            nested = data.get(field_name)
            if isinstance(nested, BaseModel):
                data[field_name] = nested.model_dump()

        notes = list(data.get("url_notes", []))
        raw_items = data.get("input_items", [])
        if isinstance(raw_items, list):
            data["input_items"] = [expand_compact_item(item) for item in raw_items]
        budget = data.get("budget")
        if isinstance(budget, dict):
            data["budget"] = expand_compact_budget(budget)

        raw_places = data.get("places", [])
        if not isinstance(raw_places, list):
            return data
        valid_places: list[PlaceCandidateInput] = []
        issues: list[CandidateValidationIssue] = []
        for index, raw_place in enumerate(raw_places):
            try:
                expanded, nested_notes = expand_compact_place(raw_place)
                valid_places.append(PlaceCandidateInput.model_validate(expanded))
                notes.extend(nested_notes)
            except (ValidationError, ValueError) as exc:
                name = raw_place.get("name") if isinstance(raw_place, dict) else None
                message = (
                    exc.errors(include_url=False)[0]["msg"]
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                issues.append(
                    CandidateValidationIssue(
                        index=index,
                        name=name,
                        code="INVALID_PLACE_CANDIDATE",
                        message=message,
                    )
                )
        data["places"] = valid_places
        data["url_notes"] = notes
        data["validation_issues"] = issues
        return data

    @staticmethod
    def _adapt_legacy_payload(data: dict[str, Any]) -> dict[str, Any]:
        intent = TripIntent.model_validate(data["intent"])
        places: list[dict[str, Any]] = []
        for candidate_value in data.get("candidates", []):
            candidate = PlaceCandidate.model_validate(candidate_value)
            coordinates = candidate.coordinates
            places.append(
                {
                    "name": candidate.name,
                    "confidence": candidate.confidence,
                    "source_places": [
                        {
                            "origin": "url" if candidate.source_url else "input",
                            "evidence_type": "legacy_candidate",
                            "source_url": candidate.source_url,
                            "evidence": candidate.name,
                        }
                    ],
                    "latitude": coordinates.latitude if coordinates else None,
                    "longitude": coordinates.longitude if coordinates else None,
                    "tags": candidate.tags,
                }
            )
        return {
            "input_ADM": intent.destination,
            "places": places,
            "input_items": [],
            "url_notes": [],
            "days": intent.days,
            "budget": {
                "level": "medium",
                "target_amount": intent.budget,
                "currency": "VND" if intent.budget is not None else None,
                "source": "legacy_trip_intent",
                "basis": "per_person",
            },
            "people": {
                "adults": intent.people,
                "children": 0,
                "infants": 0,
            },
            "short_preferences": intent.preferences,
            "short_avoids": intent.avoids,
            "special_notes": [],
        }

    @model_serializer(mode="plain")
    def serialize_compact_handoff(self) -> dict[str, Any]:
        return serialize_compact_handoff(self)

    @property
    def intent(self) -> TripIntent:
        return TripIntent(
            destination=self.input_adm,
            days=self.days,
            budget=(
                float(self.budget.target_amount)
                if self.budget.target_amount is not None
                else None
            ),
            people=self.people.total,
            preferences=self.short_preferences,
            avoids=self.short_avoids,
        )

    @property
    def candidates(self) -> list[PlaceCandidate]:
        result: list[PlaceCandidate] = []
        for place in self.places:
            primary_source = place.source_places[0]
            result.append(
                PlaceCandidate(
                    name=place.name,
                    source=place.source_tier.value,
                    source_url=primary_source.source_url,
                    coordinates=(
                        Coordinates(
                            latitude=place.latitude,
                            longitude=place.longitude,
                        )
                        if place.latitude is not None and place.longitude is not None
                        else None
                    ),
                    confidence=place.confidence,
                    tags=place.tags,
                )
            )
        return result
