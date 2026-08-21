from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.shared.contracts.itinerary import Itinerary


class EditOperation(BaseModel):
    type: Literal["remove_item", "move_item", "lock_item", "unlock_item"]
    item_id: str = Field(min_length=1)
    target_day: int | None = Field(default=None, ge=1, le=30)

    @model_validator(mode="after")
    def target_day_matches_operation(self) -> "EditOperation":
        if self.type == "move_item" and self.target_day is None:
            raise ValueError("target_day is required for move_item")
        if self.type != "move_item" and self.target_day is not None:
            raise ValueError("target_day is only valid for move_item")
        return self


class PlanEditorInput(BaseModel):
    itinerary: Itinerary
    operation: EditOperation


class PlanEditorOutput(BaseModel):
    itinerary: Itinerary
    changed: bool
    warnings: list[str] = Field(default_factory=list)


class NaturalLanguageEditModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class PlanItemEdit(NaturalLanguageEditModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    address: str | None = Field(default=None, max_length=1000)
    place_type: str | None = Field(default=None, max_length=100)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    personal_notes: str | None = Field(default=None, max_length=4000)


class NaturalLanguagePlanEdit(NaturalLanguageEditModel):
    """Gemini's structured interpretation of one user message.

    ``none`` means the message is not a plan mutation. ``clarify`` means Gemini
    identified edit intent but cannot safely resolve it to the supplied plan.
    """

    action: Literal["none", "clarify", "add", "update", "delete", "reorder"]
    confidence: float = Field(ge=0, le=1)
    day: int | None = Field(default=None, ge=1, le=30)
    item_id: str | None = Field(default=None, min_length=1, max_length=500)
    item_ids: list[str] = Field(default_factory=list, max_length=100)
    position: int | None = Field(default=None, ge=0, le=100)
    item: PlanItemEdit | None = None
    response: str | None = Field(default=None, max_length=500)
    clarification_question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def fields_match_action(self) -> "NaturalLanguagePlanEdit":
        if self.action == "clarify" and not self.clarification_question:
            raise ValueError("clarification_question is required for clarify")
        if self.action in {"add", "update", "delete", "reorder"}:
            if self.day is None or not self.response:
                raise ValueError("day and response are required for plan mutations")
        if self.action == "add" and (self.item is None or not self.item.name):
            raise ValueError("add requires item.name")
        if self.action in {"update", "delete"} and not self.item_id:
            raise ValueError(f"{self.action} requires item_id")
        if self.action == "update" and (
            self.item is None or not self.item.model_dump(exclude_none=True)
        ):
            raise ValueError("update requires at least one changed item field")
        if self.action == "reorder" and not self.item_ids:
            raise ValueError("reorder requires item_ids")
        return self


class PlanEditContext(NaturalLanguageEditModel):
    message: str = Field(min_length=1, max_length=4000)
    recent_messages: list[str] = Field(default_factory=list, max_length=6)
    plan: dict[str, Any]
