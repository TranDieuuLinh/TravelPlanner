import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import Plan


class PlanTimingStage(BaseModel):
    key: str
    label: str
    duration_seconds: float = Field(alias="durationSeconds")
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

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

    def add_stage(
        self,
        key: str,
        label: str,
        started_at: float,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.stages.append(
            PlanTimingStage(
                key=key,
                label=label,
                durationSeconds=_seconds(time.perf_counter() - started_at),
                details=details or {},
            )
        )

    def finish(self, plan: Plan) -> PlanTimingReport:
        return PlanTimingReport(
            status="completed",
            totalSeconds=_seconds(time.perf_counter() - self.started_at),
            stages=self.stages,
            dayCount=len(plan.days),
            itemCount=sum(len(day.items) for day in plan.days),
            transportLegCount=sum(len(day.transport_legs) for day in plan.days),
            unscheduledCount=len(plan.unscheduled_places),
            warningCount=len(plan.warnings),
        )


def _seconds(value: float) -> float:
    return round(max(0.0, value), 4)
