from datetime import datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, Field

from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.schema import (
    ExplorerTimingReport,
    PlaceCandidateReview,
)
from app.modules.plans.trip_intent import TripIntent
from app.modules.plans.timing import PlanTimingReport


TurnStatus = Literal[
    "queued",
    "classifying",
    "executing",
    "awaiting_confirmation",
    "completed",
    "failed",
    "cancelled",
]


class TripChatCreate(BaseModel):
    title: Annotated[str | None, Field(default=None, max_length=255)]


class TripIntentUpdateRequest(BaseModel):
    trip_intent: Annotated[TripIntent, Field(alias="tripIntent")]
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]
    expected_trip_intent_version: Annotated[
        int, Field(ge=0, alias="expectedTripIntentVersion")
    ]

    model_config = {"populate_by_name": True}


class TripChatMessageRead(BaseModel):
    id: str
    role: str
    content: str
    attachment_names: Annotated[list[str], Field(alias="attachmentNames")]
    plan_revision: Annotated[int | None, Field(alias="planRevision")]
    turn_id: Annotated[str | None, Field(default=None, alias="turnId")] = None
    message_kind: Annotated[str, Field(default="text", alias="messageKind")] = "text"
    content_blocks: Annotated[list[dict], Field(default_factory=list, alias="contentBlocks")] = []
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
    current_trip_intent: Annotated[
        TripIntent | None,
        Field(alias="currentTripIntent"),
    ]
    trip_intent_version: Annotated[int, Field(alias="tripIntentVersion")]
    trip_intent_plan_status: Annotated[
        str, Field(alias="tripIntentPlanStatus")
    ]
    candidate_reviews: Annotated[
        list[PlaceCandidateReview],
        Field(default_factory=list, alias="candidateReviews"),
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
    turns: Annotated[
        list["TripChatTurnRead"],
        Field(default_factory=list, alias="turns"),
    ] = []


class RetryCandidateResolutionsRequest(BaseModel):
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]

    model_config = {"populate_by_name": True}


class TripChatTurnCreate(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=10_000)]
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]
    client_turn_id: Annotated[
        str | None,
        Field(default=None, alias="clientTurnId", max_length=72),
    ] = None
    attachment_names: Annotated[list[str], Field(alias="attachmentNames")] = []

    model_config = {"populate_by_name": True}


class TripChatTurnRead(BaseModel):
    id: str = Field(validation_alias=AliasChoices("lifecycle_id", "id"))
    chat_id: Annotated[str, Field(alias="chatId")]
    client_turn_id: Annotated[str, Field(alias="clientTurnId")]
    status: TurnStatus
    content: str
    attachment_names: Annotated[list[str], Field(alias="attachmentNames")]
    base_revision: Annotated[int, Field(alias="baseRevision")]
    intent: str | None = None
    confidence: float | None = None
    requires_confirmation: Annotated[bool, Field(alias="requiresConfirmation")] = False
    proposed_operations: Annotated[list[dict], Field(alias="proposedOperations")] = []
    assistant_blocks: Annotated[list[dict], Field(alias="assistantBlocks")] = []
    result_summary: Annotated[dict, Field(alias="resultSummary")] = {}
    error_code: Annotated[str | None, Field(alias="errorCode")] = None
    error_message: Annotated[str | None, Field(alias="errorMessage")] = None
    created_at: Annotated[datetime, Field(alias="createdAt")]
    updated_at: Annotated[datetime, Field(alias="updatedAt")]
    plan_revision: Annotated[int | None, Field(alias="planRevision")] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


TripChatRead.model_rebuild()
