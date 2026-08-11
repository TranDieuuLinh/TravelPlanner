from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TripChatModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateTripChatInput(TripChatModel):
    title: str | None = Field(default=None, max_length=160)


class SendTripChatMessageInput(TripChatModel):
    content: str = Field(min_length=1, max_length=4000)


class TripChatMessage(TripChatModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    route: str | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
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
    messages: list[TripChatMessage] = Field(default_factory=list)


class TripChatMessageResponse(TripChatModel):
    chat: TripChat
    assistant_message: TripChatMessage
