from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.schema import (
    ExplorerContextResponse,
    ExplorerTimingReport,
)
from app.modules.plans.timing import PlanTimingReport


class TripChatCreate(BaseModel):
    title: Annotated[str | None, Field(default=None, max_length=255)]


class TripChatMessageRead(BaseModel):
    id: str
    role: str
    content: str
    attachment_names: Annotated[list[str], Field(alias="attachmentNames")]
    plan_revision: Annotated[int | None, Field(alias="planRevision")]
    created_at: Annotated[datetime, Field(alias="createdAt")]

    model_config = {"from_attributes": True, "populate_by_name": True}


class TripChatSummaryRead(BaseModel):
    id: str
    title: str
    destination: str | None
    revision: int
    has_plan: Annotated[bool, Field(alias="hasPlan")]
    created_at: Annotated[datetime, Field(alias="createdAt")]
    updated_at: Annotated[datetime, Field(alias="updatedAt")]

    model_config = {"populate_by_name": True}


class TripChatRead(TripChatSummaryRead):
    current_intake_id: Annotated[
        str | None,
        Field(default=None, alias="currentIntakeId"),
    ]
    current_plan: Annotated[Plan | None, Field(alias="currentPlan")]
    current_explorer: Annotated[
        ExplorerContextResponse | None,
        Field(alias="currentExplorer"),
    ]
    latest_explorer_timing: Annotated[
        ExplorerTimingReport | None,
        Field(default=None, alias="latestExplorerTiming"),
    ]
    latest_planner_timing: Annotated[
        PlanTimingReport | None,
        Field(default=None, alias="latestPlannerTiming"),
    ]
    messages: list[TripChatMessageRead]


class RetryCandidateResolutionsRequest(BaseModel):
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]

    model_config = {"populate_by_name": True}
