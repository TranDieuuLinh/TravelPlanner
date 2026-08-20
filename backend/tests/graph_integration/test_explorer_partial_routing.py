from types import SimpleNamespace

import pytest

from app.orchestration.routes import route_after_explorer, route_after_place_checker


def output(status: str, destination: str | None):
    return SimpleNamespace(status=status, input_adm=destination)


@pytest.mark.parametrize("status", ["ready", "partial", "clarification", "error"])
@pytest.mark.parametrize("destination", ["Hanoi", None])
def test_every_explorer_result_reaches_handoff(
    status: str, destination: str | None
) -> None:
    explorer = output(status, destination)

    assert route_after_explorer({"explorer_output": explorer}) == "place_checker"


def test_place_checker_error_and_blocked_statuses_finish() -> None:
    assert (
        route_after_place_checker({"place_output": output("error", None)}) == "finish"
    )
    assert (
        route_after_place_checker({"place_output": output("blocked", None)}) == "finish"
    )


def test_only_successful_place_checker_statuses_reach_planner() -> None:
    for status in ("completed", "conditional", "partial"):
        assert (
            route_after_place_checker({"place_output": output(status, None)})
            == "itinerary_planner"
        )
