import json
import logging

from app.modules.plans.domain.entities import Plan, PlanDay, TravelIntent
from app.modules.plans.domain.enums import (
    BudgetLevel,
    PlanKind,
    PlanStatus,
    TravelPace,
)
from app.modules.plans.timing import PlanTimingSubstage, PlanTimingTrace


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

    trace.add_stage(
        "tripThemePlanner",
        "Trip theme",
        trace.started_at,
        sub_stages=[
            PlanTimingSubstage(
                key="llmGenerate",
                label="Gemini generate",
                durationSeconds=0.25,
            )
        ],
    )
    report = trace.finish(plan)

    terminal_lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("TRAVELPLANNER_TIMING planner ")
    ]
    assert len(terminal_lines) == 1
    payload = json.loads(
        terminal_lines[0].removeprefix("TRAVELPLANNER_TIMING planner ")
    )
    assert payload["event"] == "planner_timing"
    assert payload["totalSeconds"] == report.total_seconds
    assert payload["dayCount"] == 1
    assert payload["itemCount"] == 0
    assert payload["stages"][0]["subStages"][0]["key"] == "llmGenerate"
