from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.modules.plans.dto.agent_contracts import (
    AccommodationRequirement,
    BudgetEnvelope,
    PlaceCandidateHint,
    PlanningIntent,
    TransportRequirement,
    TripPlanningSpec,
    UrlReelSignal,
    UserPlanningState,
)


class ExploreAccommodationInput(BaseModel):
    required: bool | None = None
    hotel_area: Annotated[str | None, Field(default=None, alias="hotelArea")]
    check_in_date: Annotated[str | None, Field(default=None, alias="checkInDate")]
    check_out_date: Annotated[str | None, Field(default=None, alias="checkOutDate")]
    room_count: Annotated[int | None, Field(default=None, ge=1, alias="roomCount")]
    guest_count: Annotated[int | None, Field(default=None, ge=1, alias="guestCount")]
    preferences: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ExploreTransportInput(BaseModel):
    required: bool | None = None
    preferred_modes: Annotated[list[str], Field(default_factory=list, alias="preferredModes")]
    avoid_modes: Annotated[list[str], Field(default_factory=list, alias="avoidModes")]
    include_between_places: Annotated[bool | None, Field(default=None, alias="includeBetweenPlaces")]
    include_arrival_departure: Annotated[bool | None, Field(default=None, alias="includeArrivalDeparture")]

    model_config = {"populate_by_name": True}


class ExploreBudgetInput(BaseModel):
    total_budget: Annotated[dict[str, Any] | None, Field(default=None, alias="totalBudget")]
    per_person_budget: Annotated[dict[str, Any] | None, Field(default=None, alias="perPersonBudget")]
    include_food: Annotated[bool | None, Field(default=None, alias="includeFood")]
    include_transport: Annotated[bool | None, Field(default=None, alias="includeTransport")]
    include_hotel: Annotated[bool | None, Field(default=None, alias="includeHotel")]
    include_tickets: Annotated[bool | None, Field(default=None, alias="includeTickets")]

    model_config = {"populate_by_name": True}


class ExploreTripSpecInput(BaseModel):
    days: Annotated[int | None, Field(default=None, ge=1, le=30)]
    party_size: Annotated[int | None, Field(default=None, ge=1, alias="partySize")]
    start_date: Annotated[str | None, Field(default=None, alias="startDate")]
    end_date: Annotated[str | None, Field(default=None, alias="endDate")]
    accommodation: ExploreAccommodationInput = Field(default_factory=ExploreAccommodationInput)
    transport: ExploreTransportInput = Field(default_factory=ExploreTransportInput)
    budget: ExploreBudgetInput = Field(default_factory=ExploreBudgetInput)

    model_config = {"populate_by_name": True}


class FullExploreRequest(BaseModel):
    raw_request: Annotated[str, Field(min_length=1, alias="rawRequest")]
    destination: Annotated[str, Field(min_length=1)]
    urls: list[str] = Field(default_factory=list)
    place_candidates: Annotated[list[PlaceCandidateHint], Field(default_factory=list, alias="placeCandidates")]
    user_state: Annotated[UserPlanningState, Field(default_factory=UserPlanningState, alias="userState")]
    trip_spec: Annotated[ExploreTripSpecInput, Field(default_factory=ExploreTripSpecInput, alias="tripSpec")]

    model_config = {"populate_by_name": True}


class ExploreDebug(BaseModel):
    transcript: str | None = None
    raw_extracted_text: Annotated[str | None, Field(default=None, alias="rawExtractedText")]
    url_statuses: Annotated[list[dict[str, Any]], Field(default_factory=list, alias="urlStatuses")]

    model_config = {"populate_by_name": True}


class ExploreResponse(BaseModel):
    intent: PlanningIntent
    trip_spec: Annotated[TripPlanningSpec, Field(alias="tripSpec")]
    place_candidates: Annotated[list[PlaceCandidateHint], Field(default_factory=list, alias="placeCandidates")]
    url_reel_signals: Annotated[list[UrlReelSignal], Field(default_factory=list, alias="urlReelSignals")]
    assumptions: list[str] = Field(default_factory=list)
    missing_info_questions: Annotated[list[str], Field(default_factory=list, alias="missingInfoQuestions")]
    debug: ExploreDebug = Field(default_factory=ExploreDebug)

    model_config = {"populate_by_name": True}
