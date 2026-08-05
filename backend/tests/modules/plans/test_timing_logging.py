import json
import logging

from app.modules.plans.domain.entities import Plan, PlanDay, TravelIntent
from app.modules.plans.domain.enums import (
    BudgetLevel,
    PlanKind,
    PlanStatus,
    TravelPace,
)
from app.modules.plans.timing import PlanTimingTrace


def test_planner_timing_is_logged_to_terminal(caplog) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    trace = PlanTimingTrace()
    plan = Plan(
        id="timing-plan",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Timing plan",
        destination="Hà Nội",
        intent=TravelIntent(
            destination="Hà Nội",
            days=1,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        days=[PlanDay(day=1, theme="Đi bộ", items=[])],
    )

    report = trace.finish(plan)

    terminal_lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("VSF_TIMING planner ")
    ]
    assert len(terminal_lines) == 1
    payload = json.loads(
        terminal_lines[0].removeprefix("VSF_TIMING planner ")
    )
    assert payload["event"] == "planner_timing"
    assert payload["totalSeconds"] == report.total_seconds
    assert payload["dayCount"] == 1
    assert payload["itemCount"] == 0
