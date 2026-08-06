from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.information_finder.schema import InformationCandidate, InformationSource
from app.modules.users.model import User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(email="traveler@example.com", full_name="Traveler"))
        session.commit()
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_candidate_contract_has_no_raw_provider_payload():
    candidate = InformationCandidate(
        candidateId="maps:place-1",
        placeId="place-1",
        source=InformationSource.external_provider,
        sourceRefs=["maps:place-1"],
        confidence=0.7,
        fetchedAt=datetime.now(UTC) - timedelta(days=31),
    )
    persisted = candidate.model_dump(mode="json", by_alias=True)
    assert "rawPayload" not in persisted
    assert set(persisted) == {
        "candidateId", "placeId", "source", "sourceRefs", "sourceImportNodeId",
        "candidateEntityIds", "latitude", "longitude", "confidence", "isVerified", "fetchedAt",
    }


def test_candidate_turn_is_owned_by_chat_user_after_reload(db_session):
    user = db_session.query(User).filter_by(email="traveler@example.com").one()
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Information finder")
    turn = repository.create_turn(
        chat,
        client_turn_id="finder-turn",
        content="Find a cafe",
        attachment_names=[],
        expected_revision=0,
    )
    repository.update_turn(
        turn,
        status="completed",
        assistant_blocks=[{
            "type": "candidateList",
            "candidates": [{
                "candidateId": "maps:place-1",
                "placeId": "place-1",
                "sourceRefs": ["maps:place-1"],
            }],
        }],
        result_summary={
            "candidateIds": ["maps:place-1"],
            "sourceRefs": ["maps:place-1"],
            "selectedCandidateIds": [],
            "selectedPlaceIds": [],
        },
    )

    loaded = repository.get(chat.id, user.id)
    assert loaded.messages[0].result_summary["candidateIds"] == ["maps:place-1"]
