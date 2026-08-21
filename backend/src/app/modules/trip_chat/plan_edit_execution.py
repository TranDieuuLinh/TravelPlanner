from typing import Any

from app.modules.plan_editor.public import NaturalLanguagePlanEdit
from app.modules.trip_chat.plan_snapshot import (
    add_plan_item,
    delete_plan_item,
    reorder_plan_items,
    update_plan_item,
)


def apply_plan_edit_to_output(
    output: dict[str, Any] | None,
    edit: NaturalLanguagePlanEdit,
) -> str:
    """Apply Gemini's structured decision through the manual edit primitives."""
    if edit.action == "add":
        return add_plan_item(
            output,
            day=edit.day,
            item=edit.item.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            position=edit.position,
        )
    if edit.action == "update":
        return update_plan_item(
            output,
            day=edit.day,
            item_id=edit.item_id,
            changes=edit.item.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
        )
    if edit.action == "delete":
        return delete_plan_item(output, day=edit.day, item_id=edit.item_id)
    if edit.action == "reorder":
        return reorder_plan_items(output, day=edit.day, item_ids=edit.item_ids)
    return "item_not_found"


def plan_edit_assistant(
    edit: NaturalLanguagePlanEdit,
    *,
    status: str = "updated",
) -> dict[str, Any]:
    if edit.action == "clarify":
        question = edit.clarification_question or (
            "Bạn muốn chỉnh địa điểm nào trong lịch trình?"
        )
        return _assistant(question, clarification_question=question)
    if status == "updated":
        return _assistant(edit.response or "Đã cập nhật lịch trình.")
    message = {
        "revision_conflict": "Lịch trình vừa thay đổi; bạn thử lại giúp mình nhé.",
        "day_not_found": "Không tìm thấy ngày cần chỉnh trong lịch trình.",
        "item_not_found": "Không tìm thấy địa điểm cần chỉnh trong lịch trình.",
    }.get(status, "Chưa thể cập nhật lịch trình.")
    return _assistant(message, warnings=[status])


def _assistant(
    content: str,
    *,
    clarification_question: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "content": content,
        "route": "plan_editor",
        "clarification_question": clarification_question,
        "warnings": warnings or [],
        "content_blocks": [],
        "sources": [],
        "suggestions": [],
    }
