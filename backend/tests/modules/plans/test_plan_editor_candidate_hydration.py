from types import SimpleNamespace

import pytest

from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.plan_editor.agent import CandidateHydrationError, PlanEditorAgent
from app.modules.plans.plan_editor.contract import PlanEditorOperation


class FakeChatRepository:
    def __init__(self, snapshots, reviews=()):
        self.snapshots = snapshots
        self.reviews = list(reviews)

    def load_candidate_snapshots(self, chat, turn):
        return self.snapshots

    def load_candidate_reviews(self, chat):
        return self.reviews


class FakeExplorerRepository:
    def __init__(self, node=None):
        self.node = node

    def load_candidate_node(self, intake_id, node_id, **kwargs):
        return self.node if self.node and self.node.id == node_id else None


def _chat():
    return SimpleNamespace(id="chat-1", user_id=7, current_intake_id="intake-1")


def _node(*, status="resolved", selected="kg-place-1"):
    return SimpleNamespace(
        id=11,
        candidate_key="candidate:place-1",
        entity_id="temp-place-1",
        canonical_name="Verified Place",
        candidate_name="Source Place",
        selected_entity_id=selected,
        identity_status=status,
        provider="knowledge_graph",
        match_candidates=[{"entityId": "kg-place-1"}],
        source_document_id=None,
    )


def test_verified_candidate_hydrates_identity_and_provenance():
    agent = PlanEditorAgent(
        FakeChatRepository([{
            "candidateId": "candidate:place-1",
            "name": "Source Place",
            "sourceRefs": ["https://source.test/trip"],
        }]),
        FakeExplorerRepository(_node()),
    )
    result = agent.hydrate_candidate(
        _chat(), SimpleNamespace(), PlanEditorOperation(
            type="add_place", day=1, candidateId="candidate:place-1", sourceImportNodeId=11
        ),
    )

    assert result.operation.place_id == "kg-place-1"
    assert result.operation.source_refs == ["https://source.test/trip"]
    assert result.operation.source_provider == "knowledge_graph"
    assert result.operation.identity_confidence == "high"
    assert result.operation.candidate_entity_ids == ["kg-place-1"]
    assert result.warnings == []


def test_provisional_candidate_keeps_warning_and_confidence():
    agent = PlanEditorAgent(
        FakeChatRepository([{"candidateId": "candidate:place-1", "name": "Place"}]),
        FakeExplorerRepository(_node(status="unresolved")),
    )
    result = agent.hydrate_candidate(
        _chat(), SimpleNamespace(), PlanEditorOperation(
            type="add_place", day=1, candidateId="candidate:place-1", sourceImportNodeId=11
        ),
    )
    assert result.operation.identity_confidence == "medium"
    assert result.warnings == ["candidate_identity_provisional"]


def test_foreign_or_missing_candidate_is_rejected():
    agent = PlanEditorAgent(FakeChatRepository([]), FakeExplorerRepository(_node()))
    with pytest.raises(CandidateHydrationError) as missing:
        agent.hydrate_candidate(
            _chat(), SimpleNamespace(), PlanEditorOperation(
                type="add_place", day=1, candidateId="missing"
            ),
        )
    assert missing.value.code == "CANDIDATE_NOT_FOUND"

    with pytest.raises(CandidateHydrationError) as foreign:
        agent.hydrate_candidate(
            _chat(), SimpleNamespace(), PlanEditorOperation(
                type="add_place", day=1, candidateId="candidate:place-1", sourceImportNodeId=99
            ),
        )
    assert foreign.value.code == "FOREIGN_IMPORT_NODE"


def test_ambiguous_candidate_without_stable_identity_is_rejected():
    review = PlaceCandidateReview(
        candidateId="candidate:place-1", name="Place", status="needs_review"
    )
    agent = PlanEditorAgent(
        FakeChatRepository([{"candidateId": "candidate:place-1", "name": "Place"}], [review]),
        FakeExplorerRepository(),
    )
    with pytest.raises(CandidateHydrationError) as error:
        agent.hydrate_candidate(
            _chat(), SimpleNamespace(), PlanEditorOperation(
                type="add_place", day=1, candidateId="candidate:place-1"
            ),
        )
    assert error.value.code == "CANDIDATE_IDENTITY_REQUIRED"
