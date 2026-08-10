from copy import deepcopy

from app.modules.plan_editor.contract import (
    EditOperation,
    PlanEditorInput,
    PlanEditorOutput,
)


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

