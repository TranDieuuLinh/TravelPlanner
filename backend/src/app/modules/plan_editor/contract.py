from typing import Literal

from pydantic import BaseModel, Field, model_validator

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

