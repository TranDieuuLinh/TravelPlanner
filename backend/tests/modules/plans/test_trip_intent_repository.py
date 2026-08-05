from sqlalchemy import inspect, select

from app.modules.plans.chat_model import TripChat, TripRevision
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.trip_intent import TripIntent
from app.modules.users.repository import UserRepository


def _trip_intent() -> TripIntent:
    return TripIntent.model_validate(
        {
            "destination": "Đà Lạt",
            "timing": {"days": 4},
            "travelParty": {
                "type": "family",
                "adults": 2,
                "children": 1,
                "rooms": 1,
            },
            "budget": {
                "targetAmount": 12_000_000,
                "currency": "VND",
                "level": "medium",
            },
            "notes": ["Có người lớn tuổi"],
            "preferences": {
                "interests": ["coffee", "nature"],
                "transport": {"preferredModes": ["walk", "private_car"]},
            },
            "constraints": {"items": ["Không đi bộ quá 20 phút"]},
        }
    )


def test_trip_intent_round_trips_as_chat_and_revision_snapshots(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Đà Lạt")
    expected = _trip_intent()
    payload = expected.model_dump(mode="json", by_alias=True)
    chat.current_trip_intent = payload
    db_session.add(
        TripRevision(
            id="revision-intent-json",
            chat_id=chat.id,
            revision=1,
            plan_payload={"id": "plan-1"},
            trip_intent_payload=payload,
        )
    )
    db_session.commit()

    loaded = repository.load_trip_intent(repository.get(chat.id, user.id))
    revision = db_session.scalar(
        select(TripRevision).where(TripRevision.id == "revision-intent-json")
    )

    assert loaded == expected
    assert revision is not None
    assert TripIntent.model_validate(revision.trip_intent_payload) == expected


def test_trip_persistence_uses_three_tables_without_legacy_intent_tables() -> None:
    assert TripChat.__tablename__ == "trip_chats"
    assert TripRevision.__tablename__ == "trip_revisions"
    assert "current_trip_intent" in inspect(TripChat).columns
    assert "trip_intent_payload" in inspect(TripRevision).columns
