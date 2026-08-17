from types import SimpleNamespace

from app.modules.place_checker.entertainment_pool_selection import (
    select_entertainment_pool,
)


def _candidate(
    place_id: str,
    *,
    rating: float | None = 4.7,
    reviews: int | None = 1_000,
    morning: bool = True,
    priority: str = "special_experience",
    entity_type: str = "entertainment",
):
    window = SimpleNamespace(
        start_minute=9 * 60 if morning else 13 * 60,
        end_minute=11 * 60 if morning else 20 * 60,
    )
    return SimpleNamespace(
        place_id=place_id,
        rating=rating,
        review_count=reviews,
        priority=priority,
        entity_type=entity_type,
        preferred_time_windows=[window],
        opening_hours=None,
    )


def test_keeps_only_high_bayesian_optional_entertainment() -> None:
    selected = select_entertainment_pool(
        [
            _candidate("high", rating=4.8, reviews=2_000, morning=False),
            _candidate("low", rating=3.7, reviews=2_000, morning=False),
            _candidate("missing", rating=None, reviews=None, morning=False),
        ],
        days=1,
        limit=4,
    )

    assert [candidate.place_id for candidate in selected] == ["high"]


def test_caps_optional_morning_entertainment_but_preserves_other_times() -> None:
    selected = select_entertainment_pool(
        [
            _candidate("morning-best", rating=4.9, reviews=2_000),
            _candidate("morning-second", rating=4.8, reviews=1_500),
            _candidate("afternoon", morning=False),
        ],
        days=3,
        limit=4,
    )

    assert {candidate.place_id for candidate in selected} == {
        "afternoon",
        "morning-best",
    }


def test_required_entertainment_bypasses_quality_and_morning_caps() -> None:
    selected = select_entertainment_pool(
        [
            _candidate(
                "required-low",
                rating=2.0,
                reviews=1,
                priority="user_input",
            ),
            _candidate("optional-high"),
        ],
        days=1,
        limit=1,
    )

    assert [candidate.place_id for candidate in selected] == ["required-low"]
