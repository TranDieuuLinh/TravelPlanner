from typing import Annotated
from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import CheckReport, Plan


class PlaceSuggestion(BaseModel):
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_id: str | None = Field(default=None, alias="placeId")
    image_url: str | None = Field(default=None, alias="imageUrl")
    rating: float | None = None
    review_count: int | None = Field(default=None, alias="reviewCount")
    price_level: int | None = Field(default=None, alias="priceLevel")
    place_type: str | None = Field(default=None, alias="placeType")
    phone: str | None = None
    website: str | None = None
    opening_hours: list[str] | None = Field(default=None, alias="openingHours")
    is_verified: bool = Field(default=False, alias="isVerified")
    source: str | None = None

    model_config = {"populate_by_name": True}


class AddItemRequest(BaseModel):
    day: Annotated[int, Field(ge=1, le=30)]
    place_id: Annotated[str | None, Field(default=None, alias="placeId")] = None
    name: str = Field(min_length=1, max_length=255)
    address: str | None = None
    place_type: Annotated[str, Field(alias="placeType")] = "attraction"
    time_window: Annotated[str | None, Field(default=None, alias="timeWindow")] = None
    duration_minutes: Annotated[int, Field(default=60, ge=15, le=720, alias="durationMinutes")] = 60
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = None
    personal_notes: str | None = Field(default=None, alias="personalNotes")
    tags: list[str] = Field(default_factory=list)
    position: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: Annotated[int | None, Field(default=None, ge=0, alias="reviewCount")] = None
    image_urls: Annotated[list[str] | None, Field(default=None, alias="imageUrls")] = None

    model_config = {"populate_by_name": True}


class UpdateItemRequest(BaseModel):
    place_id: Annotated[str | None, Field(default=None, alias="placeId")] = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    place_type: Annotated[str | None, Field(default=None, alias="placeType")] = None
    time_window: Annotated[str | None, Field(default=None, alias="timeWindow")] = None
    duration_minutes: Annotated[int | None, Field(default=None, ge=15, le=720, alias="durationMinutes")] = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = None
    personal_notes: str | None = Field(default=None, alias="personalNotes")
    tags: list[str] | None = None
    locked: bool | None = None

    model_config = {"populate_by_name": True}


class AddItemForm(AddItemRequest):
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]


class UpdateItemForm(UpdateItemRequest):
    expected_revision: Annotated[int, Field(ge=0, alias="expectedRevision")]


class MoveItemRequest(BaseModel):
    to_day: Annotated[int, Field(ge=1, le=30, alias="toDay")]
    position: int | None = Field(default=None, ge=0)

    model_config = {"populate_by_name": True}


class ReorderItemsRequest(BaseModel):
    item_ids: Annotated[list[str], Field(alias="itemIds")]

    model_config = {"populate_by_name": True}


class SelectTransportOptionRequest(BaseModel):
    mode: str = Field(min_length=1, max_length=40)
    option_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        alias="optionKey",
    )
    source: str | None = Field(default=None, min_length=1, max_length=80)
    distance_meters: int | None = Field(
        default=None,
        ge=0,
        alias="distanceMeters",
    )
    estimated_duration_minutes: int | None = Field(
        default=None,
        ge=0,
        alias="estimatedDurationMinutes",
    )

    model_config = {"populate_by_name": True}


class MutationResponse(BaseModel):
    plan: Plan
    affected_days: Annotated[list[int], Field(alias="affectedDays")]
    check_report: Annotated[CheckReport, Field(alias="checkReport")]

    model_config = {"populate_by_name": True}
