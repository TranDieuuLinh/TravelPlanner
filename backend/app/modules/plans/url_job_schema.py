from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.plans.explorer.schema import ExplorerTimingReport
from app.modules.plans.timing import PlanTimingReport


class UrlImportJobRead(BaseModel):
    id: str
    chat_id: Annotated[str, Field(alias="chatId")]
    source_type: Annotated[str, Field(alias="sourceType")]
    source_label: Annotated[str, Field(alias="sourceLabel")]
    url: str
    force_refresh: Annotated[bool, Field(alias="forceRefresh")]
    status: str
    queue_position: Annotated[int | None, Field(alias="queuePosition")]
    attempt_count: Annotated[int, Field(alias="attemptCount")]
    result_revision: Annotated[int | None, Field(alias="resultRevision")]
    error_code: Annotated[str | None, Field(alias="errorCode")]
    error_message: Annotated[str | None, Field(alias="errorMessage")]
    explorer_timing: Annotated[
        ExplorerTimingReport | None,
        Field(default=None, alias="explorerTiming"),
    ]
    planner_timing: Annotated[
        PlanTimingReport | None,
        Field(default=None, alias="plannerTiming"),
    ]
    created_at: Annotated[datetime, Field(alias="createdAt")]
    started_at: Annotated[datetime | None, Field(alias="startedAt")]
    finished_at: Annotated[datetime | None, Field(alias="finishedAt")]

    model_config = {"populate_by_name": True}


class UrlImportJobBatchRead(BaseModel):
    jobs: list[UrlImportJobRead]
