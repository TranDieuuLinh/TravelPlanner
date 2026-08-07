import pytest
import asyncio
from sqlalchemy import select

from app.modules.preferences.model import TravelerPreferenceSignal
from app.modules.preferences.repository import TravelerProfileRepository
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceAggregate,
    PreferenceDimension,
    PreferenceSignal,
    PreferenceSnapshot,
)
from app.modules.preferences.service import PreferenceLearningService
from app.modules.preferences.extractor import (
    DeterministicPreferenceExtractor,
    PreferenceObservation,
    PreferenceObservationResult,
    PreferencePolicy,
)
from app.modules.users.repository import UserRepository


def test_preference_learning_upgrades_legacy_array_and_accumulates_signal() -> None:
    service = PreferenceLearningService()
    snapshot = PreferenceSnapshot(
        signals=[
            PreferenceSignal(
                dimension=PreferenceDimension.category,
                value="food",
                score=0.8,
                confidence=0.9,
                sourceTypes=["user_prompt"],
            )
        ]
    )

    first = service.merge(["local"], snapshot)
    second = service.merge(
        first.model_dump(mode="json", by_alias=True),
        snapshot,
    )

    assert second.explicit == ["local"]
    assert second.scores["category:food"].observations == 2
    assert second.scores["category:food"].score == pytest.approx(0.8)
    assert second.observation_count == 2
    assert second.top_values()[0:2] == ["local", "food"]


def test_preference_learning_does_not_persist_weak_signal() -> None:
    profile = PreferenceLearningService().merge(
        {},
        PreferenceSnapshot(
            signals=[
                PreferenceSignal(
                    dimension="attribute",
                    value="photogenic",
                    score=0.2,
                    confidence=0.2,
                    sourceTypes=["url"],
                )
            ]
        ),
    )

    assert profile.scores == {}
    assert profile.observation_count == 0


def test_inferred_preference_needs_repeated_observation_before_it_is_effective() -> None:
    service = PreferenceLearningService()
    snapshot = PreferenceSnapshot(
        signals=[
            PreferenceSignal(
                dimension="pace",
                value="relaxed",
                score=0.8,
                confidence=0.9,
                sourceTypes=["user_prompt"],
            )
        ]
    )

    first = service.merge({}, snapshot)
    second = service.merge(first, snapshot)

    assert first.top_values() == []
    assert second.top_values() == ["relaxed"]


def test_preference_learning_rejects_sensitive_trait_inference() -> None:
    profile = PreferenceLearningService().merge(
        {},
        PreferenceSnapshot(
            signals=[
                PreferenceSignal(
                    dimension="attribute",
                    value="religion",
                    score=0.9,
                    confidence=0.95,
                    sourceTypes=["user_prompt"],
                )
            ]
        ),
    )

    assert profile.scores == {}


@pytest.mark.parametrize(
    "content",
    [
        "Tui cũng chả thích đi du lịch tới nơi đông ngừo đâu",
        "Mình không thích nơi đông người",
        "I don't like crowded places",
    ],
)
def test_explicit_chat_crowd_avoidance_is_normalized(content: str) -> None:
    result = asyncio.run(DeterministicPreferenceExtractor().extract(content))
    snapshot = PreferencePolicy().to_snapshot(result)
    profile = PreferenceLearningService().merge({}, snapshot)

    signal = snapshot.signals[0]
    assert signal.dimension == PreferenceDimension.setting
    assert signal.value == "uncrowded"
    assert signal.origin == "explicit"
    assert signal.source_types == ["trip_chat"]
    assert profile.top_values() == ["uncrowded"]


@pytest.mark.parametrize(
    "content",
    [
        "Mùa đông người ta thường đi đâu?",
        "Nơi này khá đông người.",
        "Mình thích nơi đông người.",
    ],
)
def test_chat_crowd_mentions_without_explicit_dislike_are_not_saved(
    content: str,
) -> None:
    result = asyncio.run(DeterministicPreferenceExtractor().extract(content))
    snapshot = PreferencePolicy().to_snapshot(result)

    assert snapshot.signals == []


def test_trip_scoped_observation_is_not_promoted_to_long_term_profile() -> None:
    snapshot = PreferencePolicy().to_snapshot(
        PreferenceObservationResult(
            observations=[
                PreferenceObservation(
                    dimension="setting",
                    value="uncrowded",
                    score=1.0,
                    confidence=0.99,
                    scope="trip",
                    explicitness="explicit",
                )
            ]
        )
    )

    assert snapshot.signals == []


def test_traveler_profile_repository_persists_signal_provenance(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    repository = TravelerProfileRepository(db_session)

    repository.save(
        user.id,
        LongTermPreferenceProfile(
            scores={
                "pace:relaxed": PreferenceAggregate(
                    score=0.8,
                    confidence=0.75,
                    observations=2,
                    sourceTypes=["user_prompt", "explorer_intent"],
                )
            },
            observationCount=2,
        ),
        evidence_intake_id="intake-preference",
    )
    repository.commit()
    db_session.expire_all()

    profile = repository.get(user.id)
    signal = db_session.scalar(
        select(TravelerPreferenceSignal).where(
            TravelerPreferenceSignal.user_id == user.id
        )
    )

    assert profile.top_values() == ["relaxed"]
    assert signal is not None
    assert signal.last_evidence_intake_id == "intake-preference"
    assert [source.source_type for source in signal.sources] == [
        "explorer_intent",
        "user_prompt",
    ]
