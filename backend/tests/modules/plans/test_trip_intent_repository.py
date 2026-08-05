from sqlalchemy import inspect, select

from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.explorer.model import ExplorerIntake
from app.modules.plans.trip_intent import TripIntent
from app.modules.plans.trip_intent_model import (
    TripIntentValue,
    TripIntentVersion,
)
from app.modules.plans.trip_intent_repository import TripIntentRepository
from app.modules.users.repository import UserRepository


def test_trip_intent_round_trips_through_normalized_tables(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    chat = TripChatRepository(db_session).create(user.id, "Đà Lạt")
    db_session.add(
        ExplorerIntake(
            id="intake-normalized-intent",
            user_id=str(user.id),
            destination="Đà Lạt",
            candidate_reviews=[],
        )
    )
    db_session.flush()
    expected = TripIntent.model_validate(
        {
            "destination": "Đà Lạt",
            "timing": {
                "days": 4,
                "startDate": "2026-09-10",
                "endDate": "2026-09-13",
                "flexibility": "fixed",
            },
            "travelParty": {
                "type": "family",
                "adults": 2,
                "children": 1,
                "infants": 0,
                "pets": 1,
                "rooms": 1,
            },
            "budget": {
                "targetAmount": 12_000_000,
                "currency": "VND",
                "level": "medium",
            },
            "notes": ["Có người lớn tuổi"],
            "preferences": {
                "travelStyle": "local",
                "pace": "relaxed",
                "interests": ["coffee", "nature"],
                "transport": {
                    "preferredModes": ["walk", "private_car"],
                },
            },
            "constraints": {
                "items": ["Không đi bộ quá 20 phút"],
                "policy": {"excludedPlaceTypes": ["cemetery"]},
            },
        }
    )

    repository = TripIntentRepository(db_session)
    row = repository.add_version(
        chat_id=chat.id,
        intake_id="intake-normalized-intent",
        revision=1,
        intent=expected,
    )
    chat.current_trip_intent_id = row.id
    db_session.commit()

    loaded = repository.get(row.id)

    assert loaded == expected
    assert db_session.scalar(
        select(TripIntentVersion).where(TripIntentVersion.id == row.id)
    ) is not None
    assert set(
        db_session.scalars(
            select(TripIntentValue.kind).where(
                TripIntentValue.trip_intent_id == row.id
            )
        )
    ) >= {"note", "interest", "constraint", "preferred_transport"}


def test_old_trip_intent_json_columns_are_not_mapped() -> None:
    from app.modules.plans.chat_model import TripChat, TripChatPlanRevision

    assert "current_explorer" not in inspect(TripChat).columns
    assert "explorer_payload" not in inspect(TripChatPlanRevision).columns
