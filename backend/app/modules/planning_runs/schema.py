from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanningRunStageRead(BaseModel):
    id: str
    sequence: int
    stage: str
    status: str
    duration_ms: int | None = Field(
        validation_alias="duration_ms",
        serialization_alias="durationMs",
    )
    input_json: Any = Field(
        validation_alias="input_json",
        serialization_alias="input",
    )
    output_json: Any = Field(
        validation_alias="output_json",
        serialization_alias="output",
    )
    error_json: dict = Field(
        validation_alias="error_json",
        serialization_alias="error",
    )
    metadata_json: dict = Field(
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime = Field(
        validation_alias="created_at",
        serialization_alias="createdAt",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PlanningRunSummaryRead(BaseModel):
    id: str
    user_id: int | None = Field(alias="userId")
    intake_id: str | None = Field(alias="intakeId")
    source: str
    mode: str
    destination: str
    status: str
    current_stage: str | None = Field(alias="currentStage")
    stage_count: int = Field(alias="stageCount")
    error_code: str | None = Field(alias="errorCode")
    summary_json: dict = Field(alias="summary")
    created_at: datetime = Field(alias="createdAt")
    completed_at: datetime | None = Field(alias="completedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PlanningRunDetailRead(PlanningRunSummaryRead):
    error_message: str | None = Field(alias="errorMessage")
    stages: list[PlanningRunStageRead]


class PlanningRunListRead(BaseModel):
    items: list[PlanningRunSummaryRead]
    total: int
    limit: int
    offset: int
