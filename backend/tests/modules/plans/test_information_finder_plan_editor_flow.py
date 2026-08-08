from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.modules.knowledge_graph.model import KnowledgeGraphImport
from app.modules.knowledge_graph.place_search import KnowledgeGraphPlaceMatch
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.information_finder import InformationFinderAgent, InformationFinderReader
from app.modules.plans.plan_editor.agent import PlanEditorAgent
from app.modules.plans.plan_mutation_schema import MoveItemRequest
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.domain.entities import Plan, PlanDay, PlanItem, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace
from app.modules.users.model import User
from app.shared.errors import AppError



def make_sample_plan() -> Plan:
    return Plan(
        id="flow-plan",
        kind=PlanKind.main,
        status=PlanStatus.locked,
        title="Hanoi flow",
        destination="Hanoi",
        intent=TravelIntent(
            destination="Hanoi",
            days=2,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        days=[
            PlanDay(
                day=1,
                theme="Old Quarter",
                items=[PlanItem(itemId="item-1-1", name="Lake", timeWindow="09:00-10:00", placeType="attraction", timelineCategory="activity", latitude=21.0285, longitude=105.8542)],
            ),
            PlanDay(
                day=2,
                theme="West Lake",
                items=[PlanItem(itemId="item-2-1", name="Pagoda", timeWindow="09:00-10:00", placeType="attraction", timelineCategory="activity", latitude=21.0478, longitude=105.8368)],
            ),
        ],
    )


class FakeGraph:
    def __init__(self, matches: list[KnowledgeGraphPlaceMatch]) -> None:
        self.matches = matches

    def search(self, query: str, destination: str | None, *, limit: int):
        return self.matches[:limit]


class FakeProvider:
    provider_name = "fake_external_places"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def search(self, query, destination, top_k, filters=None):
        self.calls += 1
        if self.error:
            raise self.error
        return []


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(email="finder-owner@example.com", full_name="Owner")
        other = User(email="finder-other@example.com", full_name="Other")
        session.add_all([owner, other])
        session.commit()
        yield session, owner, other
    Base.metadata.drop_all(engine)
    engine.dispose()


def _match() -> KnowledgeGraphPlaceMatch:
    return KnowledgeGraphPlaceMatch(
        entity_id="kg:west-lake-cafe",
        name="West Lake Cafe",
        entity_type="Restaurant",
        status="verified",
        address="Hanoi",
        latitude=21.05,
        longitude=105.82,
        source_fetched_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )


def _review() -> PlaceCandidateReview:
    return PlaceCandidateReview(
        candidateId="knowledge_graph:kg:west-lake-cafe",
        name="West Lake Cafe",
        status="needs_review",
        sourceUrls=["https://example.com/travel-source"],
        confidence=0.75,
    )


def _chat_with_candidate(session: Session, owner: User):
    repository = TripChatRepository(session)
    chat = repository.create(owner.id, "Finder to editor")
    turn = repository.create_turn(
        chat,
        client_turn_id="finder-turn",
        content="Find cafes near West Lake",
        attachment_names=[],
        expected_revision=0,
    )
    intake = KnowledgeGraphImport(
        id="finder-intake",
        import_kind="explorer_intake",
        created_by=owner.id,
        chat_id=chat.id,
        source_label="Hanoi",
        source_content="",
        candidate_reviews=[_review().model_dump(mode="json", by_alias=True)],
    )
    chat.current_intake_id = intake.id
    session.add(intake)
    session.commit()
    finder = InformationFinderAgent(
        InformationFinderReader(FakeGraph([_match()]), FakeProvider())
    )
    response = asyncio.run(finder.run(type("Context", (), {"decision": type("Decision", (), {"intent": "ask_place"})(), "turn": turn, "data": {}})()))
    assert response.result is not None
    assert response.result.candidates[0].is_verified is True
    assert "rawPayload" not in response.blocks[1]
    repository.save_conversation_response(
        repository.get(chat.id, owner.id),
        turn,
        assistant_content=response.message,
        assistant_blocks=response.blocks,
    )
    return repository, repository.get(chat.id, owner.id), turn, response.blocks


def test_information_finder_choice_adds_provisional_candidate_and_persists_provenance(db_session):
    session, owner, _ = db_session
    repository, chat, _, finder_blocks = _chat_with_candidate(session, owner)
    selection = repository.create_turn(
        chat,
        client_turn_id="selection-turn",
        content="Add that to Day 2",
        attachment_names=[],
        expected_revision=0,
    )
    repository.update_turn(selection, assistant_blocks=finder_blocks)
    editor = PlanEditorAgent(repository, object(), PlanMutationService())
    result = asyncio.run(editor.execute(
        plan=make_sample_plan(),
        chat=chat,
        turn=selection,
        intent="add_place",
        operation={
            "type": "add_place",
            "day": 2,
            "candidateId": "knowledge_graph:kg:west-lake-cafe",
            "sourceRefs": ["https://example.com/travel-source"],
        },
    ))
    assert result.warnings == ["candidate_identity_provisional"]
    added = next(item for item in result.result.plan.days[1].items if item.name == "West Lake Cafe")
    assert added.identity_confidence == "low"
    assert added.source_refs == [
        "https://example.com/travel-source",
        "knowledge_graph:kg:west-lake-cafe",
    ]
    assert added.locked is False
    assert "isVerified" not in added.model_dump(mode="json", by_alias=True)

    diff = {"beforeRevision": 0, "afterRevision": 1, "affectedDays": result.result.affected_days}
    saved = repository.save_conversation_mutation(
        chat,
        turn=selection,
        user_content=selection.content,
        assistant_content=result.summary,
        assistant_blocks=[{"type": "planDiff", **diff}],
        plan_payload=result.result.plan.model_dump(mode="json", by_alias=True),
        revision=1,
    )
    repository.update_turn(
        selection,
        status="completed",
        assistant_blocks=[{"type": "planDiff", **diff}],
        result_summary={
            "planRevision": 1,
            "sourceRefs": added.source_refs,
            "warnings": result.warnings,
        },
    )
    reloaded = repository.get(saved.id, owner.id)
    assert repository.get_revision(saved.id, 1).plan_payload["days"][1]["items"]
    assert reloaded.messages[-1].message_kind == "plan_update"
    assert reloaded.messages[-1].content_blocks[0]["affectedDays"] == [2]
    reloaded_selection = repository.get_turn(saved.id, owner.id, selection.id)
    assert reloaded_selection.result_summary["sourceRefs"] == added.source_refs
    assert "rawPayload" not in str(reloaded.messages)


def test_update_move_remove_keep_source_revision_and_checker_days(db_session):
    session, owner, _ = db_session
    repository, chat, _, finder_blocks = _chat_with_candidate(session, owner)
    editor = PlanEditorAgent(repository, object(), PlanMutationService())
    plan = make_sample_plan()
    add_turn = repository.create_turn(chat, client_turn_id="add", content="add", attachment_names=[], expected_revision=0)
    repository.update_turn(add_turn, assistant_blocks=finder_blocks)
    plan = asyncio.run(editor.execute(
        plan=plan, chat=chat, turn=add_turn,
        intent="add_place", operation={"type": "add_place", "day": 2, "candidateId": "knowledge_graph:kg:west-lake-cafe", "sourceRefs": ["https://example.com/travel-source"]},
    )).result.plan
    candidate_item = next(item for item in plan.days[1].items if item.name == "West Lake Cafe")
    update = asyncio.run(editor.execute(
        plan=plan, chat=chat, turn=repository.create_turn(chat, client_turn_id="update", content="rename", attachment_names=[], expected_revision=0),
        intent="update_place", operation={"type": "update_place", "day": 2, "itemId": candidate_item.item_id, "name": "West Lake Coffee"},
    )).result.plan
    updated = next(item for item in update.days[1].items if item.item_id == candidate_item.item_id)
    assert updated.source_refs == candidate_item.source_refs
    assert updated.source_provider == candidate_item.source_provider
    moved = editor.mutation_service.move_item(update, 2, updated.item_id, MoveItemRequest(toDay=1))
    assert moved.affected_days == [1, 2]
    removed = editor.mutation_service.remove_item(moved.plan, 1, updated.item_id)
    assert removed.affected_days == [1]
    assert all(item.item_id != updated.item_id for day in removed.plan.days for item in day.items)


def test_locked_cancel_and_stale_writer_never_mutate_current_plan(db_session):
    session, owner, other = db_session
    repository, chat, _, _ = _chat_with_candidate(session, owner)
    plan = make_sample_plan()
    plan.days[0].items[0].locked = True
    editor = PlanEditorAgent(repository, object(), PlanMutationService())
    turn = repository.create_turn(chat, client_turn_id="locked", content="change locked", attachment_names=[], expected_revision=0)
    before = plan.model_dump(mode="json")
    with pytest.raises(AppError) as error:
        asyncio.run(editor.execute(plan=plan, chat=chat, turn=turn, intent="update_place", operation={"type": "update_place", "day": 1, "itemId": "item-1-1", "name": "Changed"}))
    assert error.value.code == "LOCKED_ITEM"
    assert plan.model_dump(mode="json") == before
    repository.update_turn(turn, status="cancelled", assistant_blocks=[{"type": "text", "text": "cancelled"}])
    assert repository.get(chat.id, owner.id).revision == 0
    with pytest.raises(AppError):
        repository.get(chat.id, other.id)
    stale = repository.create_turn(chat, client_turn_id="stale", content="stale", attachment_names=[], expected_revision=0)
    repository.save_conversation_mutation(chat, turn=stale, user_content="first", assistant_content="first", assistant_blocks=[], plan_payload=before, revision=1)
    with pytest.raises(AppError) as error:
        repository.save_conversation_mutation(chat, turn=stale, user_content="stale", assistant_content="stale", assistant_blocks=[], plan_payload={"writer": "stale"}, revision=1)
    assert error.value.code == "VERSION_CONFLICT"
    assert repository.get(chat.id, owner.id).current_plan == before


def test_provider_failure_is_warning_only_and_backup_chat_is_read_only(db_session):
    session, owner, _ = db_session
    repository, chat, _, _ = _chat_with_candidate(session, owner)
    provider = FakeProvider(error=TimeoutError("fake provider only"))
    finder = InformationFinderAgent(InformationFinderReader(FakeGraph([]), provider))
    context = type("Context", (), {"decision": type("Decision", (), {"intent": "ask_place"})(), "turn": type("Turn", (), {"content": "find cafe"})(), "data": {}})()
    response = asyncio.run(finder.run(context))
    assert provider.calls == 1
    assert response.result is not None
    assert response.result.warnings == ["provider_search_failed:fake_external_places"]
    assert repository.get(chat.id, owner.id).revision == 0
    assert "rawPayload" not in str(response.blocks)
