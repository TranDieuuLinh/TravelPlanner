from typing import Literal

from pydantic import Field, model_validator

from app.modules.explorer.contract import (
    ExplorerModel,
    ExplorerPeople,
)
from app.modules.explorer.review_types import ExplorerDefaultedField
from app.shared.contracts.agent import AgentError


ExplorerReviewKind = Literal[
    "missing_fields",
    "defaults_proposed",
    "ready_for_execution",
    "error",
]


class ExplorerReviewBudget(ExplorerModel):
    amount_per_person: int | None = Field(default=None, ge=0)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    level: Literal["low", "medium", "high"] = "low"


class ExplorerReviewContext(ExplorerModel):
    input_adm: str = Field(alias="inputADM")
    days: int = Field(ge=1, le=30)
    budget: ExplorerReviewBudget
    people: ExplorerPeople
    short_preferences: list[str] = Field(default_factory=list)


class ExplorerReview(ExplorerModel):
    """Minimal Explorer-to-Supervisor handoff used before PlaceChecker."""

    kind: ExplorerReviewKind
    intake_id: str
    missing_fields: list[Literal["inputADM"]] = Field(default_factory=list)
    defaulted_fields: list[ExplorerDefaultedField] = Field(default_factory=list)
    trip_context: ExplorerReviewContext | None = None
    error: AgentError | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ExplorerReview":
        if self.kind == "missing_fields" and self.missing_fields != ["inputADM"]:
            raise ValueError("missing_fields review must request inputADM")
        if self.kind in {"defaults_proposed", "ready_for_execution"}:
            if self.trip_context is None:
                raise ValueError(f"{self.kind} review requires tripContext")
        if self.kind == "defaults_proposed" and not self.defaulted_fields:
            raise ValueError("defaults_proposed review requires defaultedFields")
        if self.kind == "error" and self.error is None:
            raise ValueError("error review requires an AgentError")
        return self
