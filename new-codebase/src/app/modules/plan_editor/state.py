from typing import TypedDict

from app.modules.plan_editor.contract import EditOperation, PlanEditorOutput
from app.shared.contracts.itinerary import Itinerary


class PlanEditorState(TypedDict, total=False):
    itinerary: Itinerary
    operation: EditOperation
    output: PlanEditorOutput

