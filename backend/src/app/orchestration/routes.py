from typing import Literal

from app.orchestration.root_state import RootState
from app.modules.explorer.public import ExplorerReview


def route_supervisor(
    state: RootState,
) -> Literal["explorer", "information_finder", "plan_editor", "finish"]:
    return state["decision"].route


def route_after_explorer(
    state: RootState,
) -> Literal["supervisor_review", "supervisor_source_summary", "place_checker"]:
    if state.get("source_action") == "summarize_source":
        return "supervisor_source_summary"
    review = ExplorerReview.model_validate(state["explorer_review"])
    return (
        "place_checker"
        if review is not None and review.kind == "ready_for_execution"
        else "supervisor_review"
    )


def route_after_place_checker(
    state: RootState,
) -> Literal["itinerary_planner", "finish"]:
    output = state["place_output"]
    status = getattr(output, "status", None)
    status_value = getattr(status, "value", status)
    return (
        "itinerary_planner"
        if status_value in {"completed", "conditional", "partial"}
        else "finish"
    )


def route_after_plan_editor(state: RootState) -> Literal["place_checker", "finish"]:
    return "place_checker" if state.get("trip_context_changed") else "finish"
