import pytest
from pydantic import ValidationError

from app.modules.plans.plan_editor import (
    PlanEditorInput,
    PlanEditorOperation,
    PlanEditorValidationError,
    validate_operation_for_intent,
)


def test_add_accepts_candidate_provenance_without_display_name():
    operation = PlanEditorOperation(
        type="add_place",
        day=2,
        candidateId="candidate-1",
        placeId="place-1",
        sourceRefs=["source-1"],
        sourceImportNodeId=7,
        candidateEntityIds=["entity-1"],
    )

    payload = operation.model_dump(by_alias=True, exclude_none=True)
    assert payload["candidateId"] == "candidate-1"
    assert payload["sourceImportNodeId"] == 7
    assert "planId" not in payload


def test_update_requires_name_or_candidate_identity():
    with pytest.raises(ValidationError):
        PlanEditorInput(
            chatId="chat-1",
            baseRevision=3,
            operation={"type": "update_place", "itemId": "item-1", "day": 1},
        )


def test_item_operations_require_item_id_and_day():
    with pytest.raises(ValidationError):
        PlanEditorInput(
            chatId="chat-1",
            baseRevision=0,
            operation={"type": "remove_place", "day": 1},
        )


def test_move_requires_valid_destination_day():
    with pytest.raises(ValidationError):
        PlanEditorOperation(
            type="move_place", itemId="item-1", day=1, toDay=31
        )


def test_intent_mismatch_is_rejected():
    operation = PlanEditorOperation(
        type="remove_place", itemId="item-1", day=1
    )
    with pytest.raises(PlanEditorValidationError):
        validate_operation_for_intent("lock_item", operation)


def test_unknown_operation_is_rejected():
    with pytest.raises(ValidationError):
        PlanEditorOperation(type="archive_place", day=1, name="x")


def test_alias_serialization_keeps_camel_case_and_revision_key():
    editor_input = PlanEditorInput(
        chatId="chat-1",
        baseRevision=4,
        operation={"type": "lock_item", "itemId": "item-1", "day": 2},
    )
    assert editor_input.model_dump(by_alias=True) == {
        "chatId": "chat-1",
        "baseRevision": 4,
        "operation": {
            "type": "lock_item",
            "day": 2,
            "toDay": None,
            "itemId": "item-1",
            "name": None,
            "candidateId": None,
            "placeId": None,
            "sourceRefs": [],
                "sourceImportNodeId": None,
                "candidateEntityIds": [],
                "sourceProvider": None,
                "identityConfidence": None,
            },
    }


def test_plan_id_is_not_a_persistence_key():
    with pytest.raises(ValidationError):
        PlanEditorInput(
            chatId="chat-1",
            baseRevision=1,
            planId="plan-1",
            operation={"type": "remove_place", "itemId": "item-1", "day": 1},
        )
