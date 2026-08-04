import pytest

from app.modules.preferences.schema import (
    PreferenceDimension,
    PreferenceSignal,
    PreferenceSnapshot,
)
from app.modules.preferences.service import PreferenceLearningService


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
