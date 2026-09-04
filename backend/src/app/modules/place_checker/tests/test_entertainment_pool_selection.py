from types import SimpleNamespace

from app.modules.place_checker.selection.entertainment import (
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
        name=place_id,
        notes=None,
        tags=[],
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


def test_entertainment_pool_requires_an_evening_window() -> None:
    selected = select_entertainment_pool(
        [
            _candidate("morning-best", rating=4.9, reviews=2_000),
            _candidate("morning-second", rating=4.8, reviews=1_500),
            _candidate("afternoon", morning=False),
        ],
        days=1,
        limit=4,
    )

    assert [candidate.place_id for candidate in selected] == ["afternoon"]


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


def test_rejects_high_rated_retail_or_commercial_service() -> None:
    souvenir = _candidate("souvenir", morning=False)
    souvenir.notes = SimpleNamespace(text="CULCAT thuộc danh mục Souvenir store")
    event_planner = _candidate("event-planner", morning=False)
    event_planner.notes = SimpleNamespace(text="Event planner")
    music_school = _candidate("Music Talent Linh Đàm", morning=False)
    paintings = _candidate("paintings", morning=False)
    paintings.notes = SimpleNamespace(text="thuộc danh mục Paintings store")
    plant_service = _candidate("indoor-garden", morning=False)
    plant_service.notes = SimpleNamespace(text="Interior plant service")
    photo_booth = _candidate("photo booth", morning=False)

    selected = select_entertainment_pool(
        [
            souvenir,
            event_planner,
            music_school,
            paintings,
            plant_service,
            photo_booth,
            _candidate("theatre", morning=False),
        ],
        days=1,
        limit=3,
    )

    assert [candidate.place_id for candidate in selected] == ["theatre"]


def test_drink_dessert_requires_a_real_drink_or_dessert_signal() -> None:
    noodle_shop = _candidate(
        "Quán Mì Vằn Thắn",
        morning=False,
        entity_type="drink_dessert",
    )
    noodle_shop.notes = SimpleNamespace(text="phục vụ món đặc trưng Mì vằn thắn")
    cafe = _candidate("Loading T Cafe", morning=False, entity_type="drink_dessert")

    selected = select_entertainment_pool(
        [noodle_shop, cafe],
        days=1,
        limit=2,
    )

    assert [candidate.place_id for candidate in selected] == ["Loading T Cafe"]
