import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.modules.knowledge_graph.model import KnowledgeGraphImport
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.explorer.schema import PlaceCandidateReview
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


def _review(candidate_id: str) -> PlaceCandidateReview:
    return PlaceCandidateReview(
        candidateId=candidate_id,
        name="Saved place",
        status="needs_review",
        sourceUrls=["https://example.com/travel"],
    )


def test_turn_candidate_blocks_and_summary_survive_reload(db_session):
    user = db_session.query(User).filter_by(email="traveler@example.com").one()
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Candidate persistence")
    turn = repository.create_turn(
        chat,
        client_turn_id="candidate-turn",
        content="Find a place",
        attachment_names=[],
        expected_revision=0,
    )
    blocks = [{
        "type": "candidateList",
        "candidates": [{
            "candidateId": "graph:place-1",
            "placeId": "place-1",
            "sourceRefs": ["knowledge_graph:place-1"],
        }],
    }]
    repository.save_conversation_response(
        repository.get(chat.id, user.id),
        turn,
        assistant_content="Choose a place.",
        assistant_blocks=blocks,
    )
    repository.update_turn(
        turn,
        status="completed",
        assistant_blocks=blocks,
        result_summary={
            "candidateIds": ["graph:place-1"],
            "sourceRefs": ["knowledge_graph:place-1"],
            "selectedCandidateIds": [],
            "selectedPlaceIds": [],
        },
    )

    reloaded = repository.get(chat.id, user.id)
    assert reloaded.messages[-1].content_blocks == blocks
    assert reloaded.messages[0].result_summary["candidateIds"] == ["graph:place-1"]
    assert "rawPayload" not in reloaded.messages[0].result_summary


def test_load_candidate_reviews_uses_current_owned_intake_only(db_session):
    user = db_session.query(User).filter_by(email="traveler@example.com").one()
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Current intake")
    chat.current_intake_id = "current-intake"
    db_session.add(KnowledgeGraphImport(
        id="current-intake",
        import_kind="explorer_intake",
        created_by=user.id,
        chat_id=chat.id,
        source_label="Hanoi",
        source_content="",
        candidate_reviews=[_review("current").model_dump(mode="json", by_alias=True)],
    ))
    db_session.add(KnowledgeGraphImport(
        id="old-intake",
        import_kind="explorer_intake",
        created_by=user.id,
        chat_id=chat.id,
        source_label="Hanoi",
        source_content="",
        candidate_reviews=[_review("old").model_dump(mode="json", by_alias=True)],
    ))
    db_session.commit()

    assert [review.candidate_id for review in repository.load_candidate_reviews(chat)] == ["current"]


def test_load_candidate_reviews_rejects_another_chat_intake(db_session):
    user = db_session.query(User).filter_by(email="traveler@example.com").one()
    repository = TripChatRepository(db_session)
    chat = repository.create(user.id, "Private chat")
    db_session.add(KnowledgeGraphImport(
        id="other-chat-intake",
        import_kind="explorer_intake",
        created_by=user.id,
        chat_id="different-chat",
        source_label="Hanoi",
        source_content="",
        candidate_reviews=[_review("private").model_dump(mode="json", by_alias=True)],
    ))
    chat.current_intake_id = "other-chat-intake"
    db_session.commit()

    assert repository.load_candidate_reviews(repository.get(chat.id, user.id)) == []
