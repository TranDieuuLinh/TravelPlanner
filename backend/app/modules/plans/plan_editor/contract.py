from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


OperationType = Literal[
    "add_place",
    "update_place",
    "remove_place",
    "move_place",
    "lock_item",
    "unlock_item",
]


class PlanEditorValidationError(ValueError):
    """Raised when an operation is not safe to pass to a mutation service."""


class PlanEditorOperation(BaseModel):
    """The single operation shared by Supervisor output and PlanEditor input.

    The operation deliberately contains no ``planId``. A conversational edit
    is scoped by the chat and its optimistic base revision instead.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: OperationType
    day: int | None = Field(default=None, ge=1, le=30)
    to_day: int | None = Field(default=None, alias="toDay", ge=1, le=30)
    item_id: str | None = Field(default=None, alias="itemId", min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    candidate_id: str | None = Field(default=None, alias="candidateId", min_length=1, max_length=128)
    place_id: str | None = Field(default=None, alias="placeId", min_length=1, max_length=128)
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs", max_length=32)
    source_import_node_id: int | None = Field(default=None, alias="sourceImportNodeId", ge=1)
    candidate_entity_ids: list[str] = Field(default_factory=list, alias="candidateEntityIds", max_length=32)
    source_provider: str | None = Field(default=None, alias="sourceProvider", max_length=64)
    identity_confidence: str | None = Field(default=None, alias="identityConfidence", max_length=32)

    @property
    def has_candidate_identity(self) -> bool:
        return bool(
            self.candidate_id
            or self.place_id
            or self.source_import_node_id
            or self.candidate_entity_ids
        )

    def validate_operation_shape(self) -> "PlanEditorOperation":
        if self.type == "add_place":
            if self.day is None:
                raise PlanEditorValidationError("add_place requires day")
            if not (self.name or self.has_candidate_identity):
                raise PlanEditorValidationError(
                    "add_place requires name or candidate identity"
                )
        elif self.type == "move_place":
            if self.item_id is None or self.day is None or self.to_day is None:
                raise PlanEditorValidationError(
                    "move_place requires itemId, day and toDay"
                )
        else:
            if self.item_id is None or self.day is None:
                raise PlanEditorValidationError(
                    f"{self.type} requires itemId and day"
                )
            if self.type == "update_place" and not (
                self.name or self.has_candidate_identity
            ):
                raise PlanEditorValidationError(
                    "update_place requires name or candidate identity"
                )
        return self


class PlanEditorInput(BaseModel):
    """Mutation envelope keyed by the conversation revision, never planId."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chat_id: str = Field(alias="chatId", min_length=1, max_length=128)
    base_revision: int = Field(alias="baseRevision", ge=0)
    operation: PlanEditorOperation

    @model_validator(mode="after")
    def validate_operation(self) -> "PlanEditorInput":
        self.operation.validate_operation_shape()
        return self


def validate_operation_for_intent(
    intent: str, operation: PlanEditorOperation
) -> PlanEditorOperation:
    """Reject a valid operation whose type does not match the routed intent."""

    if intent != operation.type:
        raise PlanEditorValidationError(
            f"operation type {operation.type!r} does not match intent {intent!r}"
        )
    operation.validate_operation_shape()
    return operation
