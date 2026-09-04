from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.explorer.public import TripContextPatch
from app.modules.information_finder.public import AnswerBlock
from app.modules.plan_editor.public import NaturalLanguagePlanEdit


SupervisorRoute = Literal[
    "explorer",
    "information_finder",
    "plan_editor",
    "finish",
]
SourceAction = Literal["plan_from_source", "summarize_source"]


class SupervisorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=4000)
    conversation_context: list[str] = Field(default_factory=list, max_length=6)
    has_source_input: bool = False
    has_itinerary: bool = False
    has_edit_operation: bool = False
    current_plan: dict[str, Any] | None = None

    destination: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=60)
    mentioned_places: list[str] = Field(default_factory=list, max_length=50)
    selected_places: list[str] = Field(default_factory=list, max_length=50)
    clarification_required: bool = False
    conversation_summary: str | None = Field(default=None, max_length=2000)
    explorer_output: dict | None = None
    pending_review_kind: str | None = Field(default=None, max_length=40)
    pending_review_fields: list[str] = Field(default_factory=list, max_length=20)


class ClassifierResult(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    route: SupervisorRoute
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=240)
    response: str | None = Field(default=None, max_length=1000)
    entity_names: list[str] = Field(default_factory=list, max_length=30)
    suggestions: list[dict[str, object]] = Field(default_factory=list, max_length=4)
    plan_edit: NaturalLanguagePlanEdit | None = None
    trip_context_patch: TripContextPatch | None = None
    source_action: SourceAction | None = None


class SupervisorDecision(ClassifierResult):
    clarification_question: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class ComposedAnswer(BaseModel):
    """Shared structured output produced after an agent has supplied facts."""

    model_config = ConfigDict(extra="forbid")

    content_blocks: list[AnswerBlock] = Field(default_factory=list)
    response: str | None = Field(default=None, max_length=4000)
