from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.plans.domain.constraint_policy import (
    ConstraintPolicy,
    GeographicScopePolicy,
)
from app.modules.plans.domain.entities import DestinationStay
from app.modules.plans.dto.agent_contracts import (
    AccommodationRequirement,
    BudgetEnvelope,
    TransportRequirement,
)
from app.modules.plans.trip_intent import (
    TravelParty,
    TripConstraints,
    TripIntent,
    TripPreferences,
    TripTiming,
)
from app.modules.plans.trip_intent_model import (
    TripIntentDestinationStay,
    TripIntentValue,
    TripIntentVersion,
)


class TripIntentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_version(
        self,
        *,
        chat_id: str,
        intake_id: str | None,
        revision: int,
        intent: TripIntent,
    ) -> TripIntentVersion:
        row = TripIntentVersion(
            id=str(uuid4()),
            chat_id=chat_id,
            intake_id=intake_id,
            revision=revision,
            destination=intent.destination,
            days=intent.timing.days,
            start_date=intent.timing.start_date,
            end_date=intent.timing.end_date,
            date_flexibility=intent.timing.flexibility,
            party_type=intent.travel_party.type,
            adults=intent.travel_party.adults,
            children=intent.travel_party.children,
            infants=intent.travel_party.infants,
            pets=intent.travel_party.pets,
            rooms=intent.travel_party.rooms,
            budget_amount=intent.budget.target_amount,
            budget_currency=intent.budget.currency,
            budget_level=intent.budget.level.value,
            travel_style=intent.preferences.travel_style,
            pace=intent.preferences.pace.value,
            accommodation_required=intent.preferences.accommodation.required,
            hotel_area=intent.preferences.accommodation.hotel_area,
            check_in_date=intent.preferences.accommodation.check_in_date,
            check_out_date=intent.preferences.accommodation.check_out_date,
            transport_required=intent.preferences.transport.required,
            include_between_places=(
                intent.preferences.transport.include_between_places
            ),
            include_arrival_departure=(
                intent.preferences.transport.include_arrival_departure
            ),
            geographic_scope=intent.constraints.policy.geographic_scope.type.value,
        )
        self.db.add(row)
        self.db.flush()
        for kind, values in self._values(intent).items():
            for position, value in enumerate(values):
                self.db.add(
                    TripIntentValue(
                        id=str(uuid4()),
                        trip_intent_id=row.id,
                        kind=kind,
                        value=value,
                        position=position,
                    )
                )
        for position, stay in enumerate(intent.timing.destination_stays):
            self.db.add(
                TripIntentDestinationStay(
                    id=str(uuid4()),
                    trip_intent_id=row.id,
                    name=stay.name,
                    duration_days=stay.duration_days,
                    start_day=stay.start_day,
                    end_day=stay.end_day,
                    position=position,
                )
            )
        return row

    def get(self, intent_id: str | None) -> TripIntent | None:
        if not intent_id:
            return None
        row = self.db.scalar(
            select(TripIntentVersion)
            .options(
                selectinload(TripIntentVersion.values),
                selectinload(TripIntentVersion.destination_stays),
            )
            .where(TripIntentVersion.id == intent_id)
        )
        return self.to_domain(row) if row is not None else None

    @staticmethod
    def to_domain(row: TripIntentVersion) -> TripIntent:
        values: dict[str, list[str]] = defaultdict(list)
        for item in sorted(row.values, key=lambda value: value.position):
            values[item.kind].append(item.value)
        stays = [
            DestinationStay(
                name=stay.name,
                durationDays=stay.duration_days,
                startDay=stay.start_day,
                endDay=stay.end_day,
            )
            for stay in sorted(row.destination_stays, key=lambda item: item.position)
        ]
        return TripIntent(
            destination=row.destination,
            timing=TripTiming(
                days=row.days,
                startDate=row.start_date,
                endDate=row.end_date,
                flexibility=row.date_flexibility,
                destinationStays=stays,
            ),
            travelParty=TravelParty(
                type=row.party_type,
                adults=row.adults,
                children=row.children,
                infants=row.infants,
                pets=row.pets,
                rooms=row.rooms,
            ),
            budget=BudgetEnvelope(
                targetAmount=(
                    int(row.budget_amount)
                    if row.budget_amount is not None
                    else None
                ),
                currency=row.budget_currency,
                level=row.budget_level,
            ),
            notes=values["note"],
            preferences=TripPreferences(
                travelStyle=row.travel_style,
                pace=row.pace,
                interests=values["interest"],
                mustVisitPlaces=values["must_visit"],
                avoidPlaces=values["avoid_place"],
                accommodation=AccommodationRequirement(
                    required=row.accommodation_required,
                    hotelArea=row.hotel_area,
                    checkInDate=row.check_in_date,
                    checkOutDate=row.check_out_date,
                    roomCount=row.rooms,
                    guestCount=row.adults + row.children + row.infants,
                    preferences=values["accommodation_preference"],
                ),
                transport=TransportRequirement(
                    required=row.transport_required,
                    preferredModes=values["preferred_transport"],
                    avoidModes=values["avoided_transport"],
                    includeBetweenPlaces=row.include_between_places,
                    includeArrivalDeparture=row.include_arrival_departure,
                ),
            ),
            constraints=TripConstraints(
                items=values["constraint"],
                policy=ConstraintPolicy(
                    excludedPlaceTypes=values["excluded_place_type"],
                    geographicScope=GeographicScopePolicy(
                        type=row.geographic_scope
                    ),
                ),
            ),
            clarifyingQuestions=values["clarifying_question"],
        )

    @staticmethod
    def _values(intent: TripIntent) -> dict[str, list[str]]:
        return {
            "note": intent.notes,
            "interest": intent.preferences.interests,
            "must_visit": intent.preferences.must_visit_places,
            "avoid_place": intent.preferences.avoid_places,
            "constraint": intent.constraints.items,
            "excluded_place_type": (
                intent.constraints.policy.excluded_place_types
            ),
            "accommodation_preference": (
                intent.preferences.accommodation.preferences
            ),
            "preferred_transport": [
                mode.value for mode in intent.preferences.transport.preferred_modes
            ],
            "avoided_transport": [
                mode.value for mode in intent.preferences.transport.avoid_modes
            ],
            "clarifying_question": intent.clarifying_questions,
        }
