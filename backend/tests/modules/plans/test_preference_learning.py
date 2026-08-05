import pytest
from sqlalchemy import select

from app.modules.plans.explorer.model import ExplorerIntake
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


def test_traveler_profile_repository_persists_signal_provenance(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    db_session.add(
        ExplorerIntake(
            id="intake-preference",
            user_id=str(user.id),
            destination="Hà Nội",
            candidate_reviews=[],
        )
    )
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
