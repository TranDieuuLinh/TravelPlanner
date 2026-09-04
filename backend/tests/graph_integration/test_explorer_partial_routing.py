from types import SimpleNamespace

from app.orchestration.routes import route_after_explorer, route_after_place_checker


def output(status: str, destination: str | None):
    return SimpleNamespace(status=status, input_adm=destination)


def test_only_ready_review_reaches_place_checker() -> None:
    review = {
        "kind": "ready_for_execution",
        "intakeId": "ready-1",
        "tripContext": {
            "inputADM": "Hanoi",
            "days": 3,
            "budget": {"level": "low"},
            "people": {"adults": 2},
            "shortPreferences": [],
        },
    }
    assert route_after_explorer({"explorer_review": review}) == "place_checker"


def test_source_summary_bypasses_review_and_place_checker() -> None:
    assert (
        route_after_explorer(
            {
                "source_action": "summarize_source",
                "explorer_review": {
                    "kind": "missing_fields",
                    "intakeId": "summary-1",
                    "missingFields": ["inputADM"],
                },
            }
        )
        == "supervisor_source_summary"
    )


def test_missing_defaults_and_error_reviews_return_to_supervisor() -> None:
    reviews = [
        {
            "kind": "missing_fields",
            "intakeId": "missing-1",
            "missingFields": ["inputADM"],
        },
        {
            "kind": "defaults_proposed",
            "intakeId": "defaults-1",
            "defaultedFields": ["days"],
            "tripContext": {
                "inputADM": "Hanoi",
                "days": 3,
                "budget": {"level": "low"},
                "people": {"adults": 2},
                "shortPreferences": [],
            },
        },
        {
            "kind": "error",
            "intakeId": "error-1",
            "error": {"code": "EXPLORER_FAILED", "message": "failed"},
        },
    ]
    for review in reviews:
        assert route_after_explorer({"explorer_review": review}) == "supervisor_review"


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
