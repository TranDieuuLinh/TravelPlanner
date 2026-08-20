from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerModel,
    ExplorerOutput,
    ExplorerPeople,
    ExplorerPlace,
    ItemType,
    PlaceSource,
    RequestedItem,
)
from app.modules.explorer.ports import InsightCatalog, TagCatalog
from app.modules.explorer.trip_defaults import timezone_for_destination

ScalarOperation = Literal[
    "set", "increment", "decrement", "reset_to_default", "keep"
]
CollectionOperation = Literal["add", "remove", "replace", "clear", "keep"]


class StringScalarPatch(ExplorerModel):
    operation: ScalarOperation
    value: str | None = None

    @model_validator(mode="after")
    def valid_value(self) -> "StringScalarPatch":
        if self.operation == "set" and not self.value:
            raise ValueError("set requires value")
        if self.operation in {"increment", "decrement"}:
            raise ValueError("string fields do not support increment or decrement")
        return self


class IntegerScalarPatch(ExplorerModel):
    operation: ScalarOperation
    value: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_value(self) -> "IntegerScalarPatch":
        if self.operation in {"set", "increment", "decrement"} and self.value is None:
            raise ValueError(f"{self.operation} requires value")
        return self


class PeopleValues(ExplorerModel):
    adults: int = Field(default=0, ge=0, le=100)
    children: int = Field(default=0, ge=0, le=100)
    infants: int = Field(default=0, ge=0, le=100)

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants


class PeoplePatch(ExplorerModel):
    operation: ScalarOperation
    value: PeopleValues | None = None

    @model_validator(mode="after")
    def valid_value(self) -> "PeoplePatch":
        if self.operation in {"set", "increment", "decrement"}:
            if self.value is None or self.value.total < 1:
                raise ValueError(f"{self.operation} requires at least one traveler")
        return self


class BudgetValues(ExplorerModel):
    amount_per_person: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    level: Literal["low", "medium", "high"] | None = None


class BudgetPatch(ExplorerModel):
    operation: ScalarOperation
    value: BudgetValues | None = None

    @model_validator(mode="after")
    def valid_value(self) -> "BudgetPatch":
        if self.operation in {"set", "increment", "decrement"}:
            if self.value is None:
                raise ValueError(f"{self.operation} requires value")
        if self.operation in {"increment", "decrement"}:
            if not self.value or self.value.amount_per_person is None:
                raise ValueError(f"budget {self.operation} requires amountPerPerson")
        return self


class PlacePatchValue(ExplorerModel):
    name: str = Field(min_length=1, max_length=200)
    address_hint: str | None = Field(default=None, max_length=300)


class ItemPatchValue(ExplorerModel):
    name: str = Field(min_length=1, max_length=160)
    item_type: ItemType | None = None
    related_place_name: str | None = Field(default=None, max_length=200)


class StringCollectionPatch(ExplorerModel):
    operation: CollectionOperation
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_values(self) -> "StringCollectionPatch":
        if self.operation in {"add", "remove", "replace"} and not self.values:
            raise ValueError(f"{self.operation} requires values")
        return self


class PlaceCollectionPatch(ExplorerModel):
    operation: CollectionOperation
    values: list[PlacePatchValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_values(self) -> "PlaceCollectionPatch":
        if self.operation in {"add", "remove", "replace"} and not self.values:
            raise ValueError(f"{self.operation} requires values")
        return self


class ItemCollectionPatch(ExplorerModel):
    operation: CollectionOperation
    values: list[ItemPatchValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_values(self) -> "ItemCollectionPatch":
        if self.operation in {"add", "remove", "replace"} and not self.values:
            raise ValueError(f"{self.operation} requires values")
        if self.operation in {"add", "replace"} and any(
            value.item_type is None for value in self.values
        ):
            raise ValueError(f"{self.operation} requires itemType")
        return self


class TripContextPatch(ExplorerModel):
    input_adm: StringScalarPatch | None = Field(default=None, alias="inputADM")
    days: IntegerScalarPatch | None = None
    people: PeoplePatch | None = None
    budget: BudgetPatch | None = None
    places: PlaceCollectionPatch | None = None
    input_items: ItemCollectionPatch | None = None
    short_preferences: StringCollectionPatch | None = None
    short_avoids: StringCollectionPatch | None = None
    special_notes: StringCollectionPatch | None = None


def apply_trip_context_patch(
    output: ExplorerOutput,
    patch: TripContextPatch,
    *,
    raw_user_message: str,
    tag_catalog: TagCatalog | None = None,
    insight_catalog: InsightCatalog | None = None,
) -> ExplorerOutput:
    """Apply one user turn after Explorer extraction and before Place Checker."""
    if output.status == "error":
        raise ValueError("cannot patch an Explorer error output")
    update: dict = {}
    adm = _apply_adm(output.input_adm, patch.input_adm)
    update["input_adm"] = adm
    update["days"] = _apply_integer(output.days, patch.days, default=3, maximum=30)
    people = _apply_people(output.people, patch.people)
    budget = _apply_budget(output.budget, patch.budget)
    update["people"] = people
    update["budget"] = budget
    update["places"] = _apply_places(output.places or [], patch.places, raw_user_message)
    update["input_items"] = _apply_items(
        output.input_items or [], patch.input_items, raw_user_message
    )
    preferences = _apply_strings(
        output.short_preferences, patch.short_preferences, tag_catalog
    )
    avoids = _apply_strings(output.short_avoids, patch.short_avoids, tag_catalog)
    if not output.input_adm and adm and insight_catalog is not None:
        preferences, avoids = insight_catalog.enrich(
            budget_level=budget.level,
            children=people.children,
            infants=people.infants,
            preferences=preferences,
            avoids=avoids,
            seed=f"{output.intake_id}:{adm}:{budget.level}",
        )
    update["short_preferences"] = [value for value in preferences if value not in avoids]
    update["short_avoids"] = avoids
    update["special_notes"] = _apply_strings(
        output.special_notes, patch.special_notes, None
    )
    update["timezone"] = timezone_for_destination(adm)
    update["status"] = "partial" if adm and output.status == "partial" else (
        "ready" if adm else "clarification"
    )
    update["clarification_question"] = (
        None if adm else "Bạn muốn đi tỉnh hoặc thành phố nào?"
    )
    return output.model_copy(update=update)


def _apply_adm(current: str | None, patch: StringScalarPatch | None) -> str | None:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "reset_to_default":
        return None
    return patch.value.strip() if patch.value else current


def _apply_integer(current: int, patch, *, default: int, maximum: int) -> int:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "reset_to_default":
        return default
    if patch.operation == "set":
        return min(patch.value, maximum)
    delta = patch.value if patch.operation == "increment" else -patch.value
    return min(max(1, current + delta), maximum)


def _apply_people(current: ExplorerPeople, patch: PeoplePatch | None) -> ExplorerPeople:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "reset_to_default":
        return ExplorerPeople()
    values = patch.value or PeopleValues()
    if patch.operation == "set":
        result = values
    else:
        sign = 1 if patch.operation == "increment" else -1
        result = PeopleValues(
            adults=max(0, current.adults + sign * values.adults),
            children=max(0, current.children + sign * values.children),
            infants=max(0, current.infants + sign * values.infants),
        )
    if result.total < 1:
        raise ValueError("a trip must keep at least one traveler")
    return ExplorerPeople.model_validate(result.model_dump())


def _apply_budget(current: ExplorerBudget, patch: BudgetPatch | None) -> ExplorerBudget:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "reset_to_default":
        return ExplorerBudget(level="low", source="default", basis="per_person")
    values = patch.value or BudgetValues()
    amount = values.amount_per_person
    if patch.operation in {"increment", "decrement"}:
        base = current.target_amount or 0
        sign = 1 if patch.operation == "increment" else -1
        amount = max(0, base + sign * (amount or 0))
    return ExplorerBudget(
        level=values.level or current.level,
        targetAmount=amount,
        currency=values.currency or current.currency,
        source="raw_prompt",
        basis="per_person",
    )


def _apply_places(current, patch, raw_message: str) -> list[ExplorerPlace]:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "clear":
        return []
    remove_keys = {_key(value.name) for value in patch.values}
    if patch.operation == "remove":
        return [value for value in current if _key(value.name) not in remove_keys]
    added = [
        ExplorerPlace(
            name=value.name,
            addressHint=value.address_hint,
            confidence=1,
            sourcePlaces=[PlaceSource(
                origin="input",
                evidenceType="raw_prompt",
                evidence=raw_message.strip() or value.name,
                addressHint=value.address_hint,
            )],
        )
        for value in patch.values
    ]
    return _merge_by_name([] if patch.operation == "replace" else current, added)


def _apply_items(current, patch, raw_message: str) -> list[RequestedItem]:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "clear":
        return []
    remove_keys = {_key(value.name) for value in patch.values}
    if patch.operation == "remove":
        return [value for value in current if _key(value.name) not in remove_keys]
    actions = {"food": "eat", "drink": "drink", "activity": "experience"}
    added = [
        RequestedItem(
            name=value.name,
            itemType=value.item_type or "activity",
            action=actions[value.item_type or "activity"],
            relatedPlaceName=value.related_place_name,
            evidence=raw_message.strip() or value.name,
            confidence=1,
        )
        for value in patch.values
    ]
    return _merge_by_name([] if patch.operation == "replace" else current, added)


def _apply_strings(current, patch, tag_catalog: TagCatalog | None) -> list[str]:
    if patch is None or patch.operation == "keep":
        return current
    if patch.operation == "clear":
        return []
    values = patch.values
    if tag_catalog is not None:
        values = tag_catalog.resolve(values)
    remove_keys = {_key(value) for value in values}
    if patch.operation == "remove":
        return [value for value in current if _key(value) not in remove_keys]
    base = [] if patch.operation == "replace" else current
    return list(dict.fromkeys([*base, *values]))


def _merge_by_name(current: list, added: list) -> list:
    result = list(current)
    positions = {_key(value.name): index for index, value in enumerate(result)}
    for value in added:
        key = _key(value.name)
        if key in positions:
            result[positions[key]] = value
        else:
            positions[key] = len(result)
            result.append(value)
    return result


def _key(value: str) -> str:
    return " ".join(value.casefold().split())
