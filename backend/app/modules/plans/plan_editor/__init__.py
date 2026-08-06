"""Shared contract for conversational and direct plan editing."""

from .contract import (
    PlanEditorInput,
    PlanEditorOperation,
    PlanEditorValidationError,
    OperationType,
    validate_operation_for_intent,
)

__all__ = [
    "OperationType",
    "PlanEditorInput",
    "PlanEditorOperation",
    "PlanEditorValidationError",
    "validate_operation_for_intent",
]
