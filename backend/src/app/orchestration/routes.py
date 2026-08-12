from typing import Literal

from app.orchestration.root_state import RootState


def route_supervisor(
    state: RootState,
) -> Literal["explorer", "information_finder", "plan_editor", "finish"]:
    return state["decision"].route


def route_after_explorer(
    state: RootState,
) -> Literal["place_checker", "finish"]:
    output = state["explorer_output"]
    return "place_checker" if output.status == "ready" else "finish"


def route_after_place_checker(
    state: RootState,
) -> Literal["itinerary_planner", "finish"]:
    output = state["place_output"]
    status = getattr(output, "status", None)
    status_value = getattr(status, "value", status)
    return "finish" if status_value == "blocked" else "itinerary_planner"
