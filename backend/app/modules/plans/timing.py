import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import Plan


terminal_logger = logging.getLogger("uvicorn.error")


class PlanTimingSubstage(BaseModel):
    key: str
    label: str
    duration_seconds: float = Field(alias="durationSeconds")
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class PlanTimingStage(BaseModel):
    key: str
    label: str
    duration_seconds: float = Field(alias="durationSeconds")
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    sub_stages: list[PlanTimingSubstage] = Field(
        default_factory=list,
        alias="subStages",
    )

    model_config = {"populate_by_name": True}


class PlanTimingReport(BaseModel):
    status: str
    total_seconds: float = Field(alias="totalSeconds")
    stages: list[PlanTimingStage] = Field(default_factory=list)
    day_count: int = Field(alias="dayCount")
    item_count: int = Field(alias="itemCount")
    transport_leg_count: int = Field(alias="transportLegCount")
    unscheduled_count: int = Field(alias="unscheduledCount")
    warning_count: int = Field(alias="warningCount")

    model_config = {"populate_by_name": True}


@dataclass
class PlanTimingTrace:
    started_at: float = field(default_factory=time.perf_counter)
    stages: list[PlanTimingStage] = field(default_factory=list)
    on_update: Callable[[PlanTimingReport], None] | None = None

    def add_stage(
        self,
        key: str,
        label: str,
        started_at: float,
        *,
        details: dict[str, Any] | None = None,
        sub_stages: list[PlanTimingSubstage] | None = None,
    ) -> None:
        self.stages.append(
            PlanTimingStage(
                key=key,
                label=label,
                durationSeconds=_seconds(time.perf_counter() - started_at),
                details=details or {},
                subStages=sub_stages or [],
            )
        )
        if self.on_update is not None:
            self.on_update(self.snapshot())

    def snapshot(self) -> PlanTimingReport:
        return PlanTimingReport(
            status="running",
            totalSeconds=_seconds(time.perf_counter() - self.started_at),
            stages=list(self.stages),
            dayCount=0,
            itemCount=0,
            transportLegCount=0,
            unscheduledCount=0,
            warningCount=0,
        )

    def finish(self, plan: Plan) -> PlanTimingReport:
        report = PlanTimingReport(
            status="completed",
            totalSeconds=_seconds(time.perf_counter() - self.started_at),
            stages=self.stages,
            dayCount=len(plan.days),
            itemCount=sum(len(day.items) for day in plan.days),
            transportLegCount=sum(len(day.transport_legs) for day in plan.days),
            unscheduledCount=len(plan.unscheduled_places),
            warningCount=len(plan.warnings),
        )
        if self.on_update is not None:
            self.on_update(report)
        terminal_logger.info(
            "VSF_TIMING planner %s",
            json.dumps(
                {
                    "event": "planner_timing",
                    **report.model_dump(mode="json", by_alias=True),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        return report


def _seconds(value: float) -> float:
    return round(max(0.0, value), 4)
