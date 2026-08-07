import json
import logging

from app.modules.plans.domain.entities import Plan, PlanDay, TravelIntent
from app.modules.plans.domain.enums import (
    BudgetLevel,
    PlanKind,
    PlanStatus,
    TravelPace,
)
from app.modules.plans.conversation_service import _log_prompt_planner_timing
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


def test_timing_can_include_preflight_completed_before_workflow_trace() -> None:
    trace = PlanTimingTrace()

    trace.add_completed_stage(
        "capacityPreflight",
        "Capacity preflight",
        duration_seconds=0.25,
        details={"preflightMatrixBuildCount": 1},
    )

    assert trace.stages[0].duration_seconds == 0.25
    assert trace.stages[0].details["preflightMatrixBuildCount"] == 1
    assert trace.snapshot().total_seconds >= 0.25


def test_raw_prompt_planner_timing_is_correlated_without_prompt_text(caplog) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    _log_prompt_planner_timing(
        turn_id="turn-raw-1",
        source_type="raw_prompt",
        status="succeeded",
        wall_seconds=2.75,
        explorer_timing={"totalSeconds": 0.5},
        planner_timing={
            "status": "completed",
            "totalSeconds": 2.0,
            "stages": [
                {
                    "key": "placeSelector",
                    "label": "Place selector",
                    "durationSeconds": 1.25,
                    "details": {"selectedPlaceCount": 3},
                    "subStages": [],
                }
            ],
            "dayCount": 2,
            "itemCount": 3,
            "transportLegCount": 1,
            "unscheduledCount": 0,
            "warningCount": 0,
        },
        error_code=None,
    )

    line = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith(
            "TRAVELPLANNER_TIMING prompt_planner "
        )
    )
    payload = json.loads(
        line.removeprefix("TRAVELPLANNER_TIMING prompt_planner ")
    )
    assert payload["event"] == "prompt_planner_timing"
    assert payload["turnId"] == "turn-raw-1"
    assert payload["sourceType"] == "raw_prompt"
    assert payload["explorerSeconds"] == 0.5
    assert payload["plannerSeconds"] == 2.0
    assert payload["plannerTiming"]["stages"][0]["key"] == "placeSelector"
    assert "prompt" not in payload
