from copy import deepcopy

from app.modules.plan_editor.contract import (
    NaturalLanguagePlanEdit,
    PlanEditContext,
    PlanEditorInput,
    PlanEditorOutput,
)
from app.modules.plan_editor.ports import PlanEditIntentResolver


class PlanEditorService:
    def edit(self, payload: PlanEditorInput) -> PlanEditorOutput:
        itinerary = deepcopy(payload.itinerary)
        operation = payload.operation
        source_day = None
        selected_item = None

        for day in itinerary.days:
            for item in day.items:
                if item.item_id == operation.item_id:
                    source_day = day
                    selected_item = item
                    break
            if selected_item is not None:
                break

        if selected_item is None or source_day is None:
            return PlanEditorOutput(
                itinerary=itinerary,
                changed=False,
                warnings=[f"Item {operation.item_id} was not found."],
            )

        if operation.type == "remove_item":
            if selected_item.locked:
                return PlanEditorOutput(
                    itinerary=itinerary,
                    changed=False,
                    warnings=["A locked item cannot be removed."],
                )
            source_day.items.remove(selected_item)
        elif operation.type == "move_item":
            if selected_item.locked:
                return PlanEditorOutput(
                    itinerary=itinerary,
                    changed=False,
                    warnings=["A locked item cannot be moved."],
                )
            target_day = next(
                (day for day in itinerary.days if day.day == operation.target_day),
                None,
            )
            if target_day is None:
                return PlanEditorOutput(
                    itinerary=itinerary,
                    changed=False,
                    warnings=[f"Day {operation.target_day} does not exist."],
                )
            source_day.items.remove(selected_item)
            target_day.items.append(selected_item)
        elif operation.type == "lock_item":
            selected_item.locked = True
        elif operation.type == "unlock_item":
            selected_item.locked = False

        itinerary.revision += 1
        return PlanEditorOutput(itinerary=itinerary, changed=True)


class NaturalLanguagePlanEditor:
    """Resolve natural-language edits without deterministic intent heuristics."""

    def __init__(
        self,
        resolver: PlanEditIntentResolver,
        *,
        confidence_threshold: float = 0.72,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between zero and one")
        self._resolver = resolver
        self._confidence_threshold = confidence_threshold

    async def interpret(
        self,
        message: str,
        planner_output: dict,
        *,
        recent_messages: list[str] | None = None,
    ) -> NaturalLanguagePlanEdit:
        context = PlanEditContext(
            message=message,
            recent_messages=[item[-500:] for item in (recent_messages or [])[-6:]],
            plan=compact_plan_for_edit(planner_output),
        )
        edit = await self._resolver.resolve(context)
        return validate_natural_language_plan_edit(
            edit,
            context.plan,
            confidence_threshold=self._confidence_threshold,
        )


def compact_plan_for_edit(planner_output: dict) -> dict:
    """Project a planner snapshot to the small context Gemini needs."""
    days = []
    for raw_day in planner_output.get("days", []):
        if not isinstance(raw_day, dict):
            continue
        items = []
        for raw_item in raw_day.get("stops", []):
            if not isinstance(raw_item, dict):
                continue
            items.append(
                {
                    "itemId": raw_item.get("itemId"),
                    "name": raw_item.get("name"),
                    "address": raw_item.get("address"),
                    "durationMinutes": raw_item.get("durationMinutes"),
                    "personalNotes": raw_item.get("personalNotes"),
                }
            )
        days.append({"day": raw_day.get("day"), "items": items})
    return {"destination": planner_output.get("destination"), "days": days}


def validate_natural_language_plan_edit(
    edit: NaturalLanguagePlanEdit,
    plan: dict,
    *,
    confidence_threshold: float = 0.72,
) -> NaturalLanguagePlanEdit:
    """Reject unresolved model references without keyword-based intent rules."""
    if edit.action == "none":
        return edit
    if edit.confidence < confidence_threshold:
        return _clarification(
            "Bạn muốn thêm, sửa, xóa hay sắp xếp địa điểm nào trong lịch trình?"
        )
    if edit.action == "clarify":
        return edit
    day = next(
        (item for item in plan.get("days", []) if item.get("day") == edit.day),
        None,
    )
    if day is None:
        return _clarification(
            f"Lịch trình không có ngày {edit.day}; bạn muốn chỉnh ngày nào?"
        )
    known_ids = {
        str(item.get("itemId"))
        for item in day.get("items", [])
        if item.get("itemId")
    }
    if edit.action in {"update", "delete"} and edit.item_id not in known_ids:
        return _clarification(
            "Mình chưa xác định được đúng địa điểm cần chỉnh; bạn nói rõ tên giúp mình nhé."
        )
    if edit.action == "reorder" and (
        len(edit.item_ids) != len(known_ids) or set(edit.item_ids) != known_ids
    ):
        return _clarification(
            "Mình chưa xác định được đầy đủ thứ tự địa điểm; bạn mô tả lại thứ tự mong muốn nhé."
        )
    return edit


def _clarification(question: str) -> NaturalLanguagePlanEdit:
    return NaturalLanguagePlanEdit(
        action="clarify",
        confidence=1.0,
        clarification_question=question,
    )
