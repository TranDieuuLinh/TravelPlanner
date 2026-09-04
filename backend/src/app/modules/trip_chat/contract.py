from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.information_finder.public import AnswerBlock


class TripChatModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateTripChatInput(TripChatModel):
    title: str | None = Field(default=None, max_length=160)


class SendTripChatMessageInput(TripChatModel):
    content: str = Field(min_length=1, max_length=4000)


class UpdatePersonalNotesInput(TripChatModel):
    expected_revision: int = Field(ge=0)
    personal_notes: str | None = Field(default=None, max_length=4000)


class UpdateAccommodationInput(TripChatModel):
    expected_revision: int = Field(ge=0)
    place_id: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    address: str | None = Field(default=None, max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    personal_notes: str | None = Field(default=None, max_length=4000)


class ReplacePlanItemInput(TripChatModel):
    expected_revision: int = Field(ge=0)
    place_id: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=500)
    address: str | None = Field(default=None, max_length=1000)
    place_type: str | None = Field(default=None, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    opening_hours: list[str] | None = Field(default=None, max_length=50)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    cost_per_person: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=2048)


class SelectTransportOptionInput(TripChatModel):
    expected_revision: int = Field(ge=0)
    mode: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=160)
    distance_meters: int = Field(ge=0)
    estimated_duration_minutes: int = Field(ge=0)
    geometry_coordinates: list[tuple[float, float]] = Field(
        default_factory=list,
        max_length=10_000,
    )
    verified: bool = False
    estimated_cost_per_person: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fetched_at: str | None = Field(default=None, max_length=64)
    details: dict[str, Any] | None = None


PlanNoteUpdateStatus = Literal[
    "updated", "chat_not_found", "revision_conflict", "item_not_found"
]

AccommodationUpdateStatus = Literal[
    "updated", "chat_not_found", "revision_conflict", "accommodation_not_found"
]

TransportSelectionStatus = Literal[
    "updated", "chat_not_found", "revision_conflict", "day_not_found", "leg_not_found"
]

PlanItemMutationStatus = Literal[
    "updated",
    "chat_not_found",
    "revision_conflict",
    "day_not_found",
    "item_not_found",
    "unscheduled_not_found",
]


class TripChatMessage(TripChatModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    route: str | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    content_blocks: list[AnswerBlock] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class TripChatSummary(TripChatModel):
    id: str
    title: str
    revision: int
    has_itinerary: bool
    created_at: datetime
    updated_at: datetime


class TripChat(TripChatSummary):
    thread_id: str
    current_itinerary: dict[str, Any] | None = None
    current_planner_output: dict[str, Any] | None = None
    messages: list[TripChatMessage] = Field(default_factory=list)


class TripChatBootstrap(TripChatModel):
    chats: list[TripChatSummary] = Field(default_factory=list)
    active_chat: TripChat | None = None


class TripChatMessageResponse(TripChatModel):
    chat: TripChat
    assistant_message: TripChatMessage
