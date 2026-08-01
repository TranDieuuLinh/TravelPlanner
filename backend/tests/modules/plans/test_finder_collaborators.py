from __future__ import annotations

from app.modules.plans.domain.entities import (
    FinderPlanStatus,
    PlanItem,
    PlanTransportLeg,
    UserStatus,
)
from app.modules.plans.finder.day_style_selector import (
    DayStyle,
    classify_place,
    select_day_style,
)
from app.modules.plans.finder.place_tool import EmptyFinderPlaceTool, FinderPlace
from app.modules.plans.finder.skeleton_builder import DayBlock, DaySkeletonBuilder
from app.modules.plans.finder.status_tracker import FinderStatusTracker
from app.modules.plans.finder.time_windows import (
    format_clock,
    format_clock_window,
    parse_clock_minutes,
    parse_unbounded_clock_minutes,
    window_duration,
)
from app.modules.plans.finder.timeline_fitter import TimelineFitter


def test_time_windows_preserve_bounded_and_unbounded_clock_semantics() -> None:
    assert parse_clock_minutes("available after 08:30") == 510
    assert parse_clock_minutes("24:00") is None
    assert parse_unbounded_clock_minutes("24:00") == 1_440
    assert parse_unbounded_clock_minutes("23:30-24:00") == 1_410
    assert format_clock(1_440) == "24:00"
    assert format_clock(1_440, bound_to_day=True) == "23:59"
    assert format_clock_window(1_410, 30) == "23:30-24:00"
    assert window_duration("23:30-24:00") == 30
    assert window_duration("22:00-22:45") == 45
    assert window_duration("not a window") is None


def test_timeline_fitter_shifts_items_and_rejects_midnight_overflow() -> None:
    # Window duration of 60 min starting at 23:00 ends at 24:00, triggering
    # overflow (>= 24:00 boundary) in the fitter.
    late = _item("late", "23:00-24:00", 60)
    warnings: list[str] = []
    status = FinderPlanStatus()

    result = TimelineFitter().fit(
        [late],
        [],
        day=1,
        warnings=warnings,
        plan_status=status,
    )

    assert result.items == []
    assert [item.name for item in result.overflow_items] == ["late"]
    assert any("reach or exceed 24:00" in warning for warning in warnings)
    assert status.warnings == warnings


def test_timeline_fitter_warns_when_day_extends_past_evening() -> None:
    long_block = _item("long", "18:00-22:00", 240)
    warnings: list[str] = []
    status = FinderPlanStatus()

    result = TimelineFitter().fit(
        [long_block],
        [],
        day=2,
        warnings=warnings,
        plan_status=status,
    )

    assert [item.name for item in result.items] == ["long"]
    assert any("ends after 21:00" in warning for warning in warnings)


def test_status_tracker_applies_and_rolls_back_activity_effects() -> None:
    candidate = FinderPlace(
        placeId="museum",
        name="Museum",
        placeType="attraction",
        regionKey="vn,ha-noi",
        tags=["culture"],
        typicalDurationMinutes=60,
        activityIntensity="light",
    )
    block = DayBlock("main_activity", "09:00-10:00", 60, True)
    user_status = UserStatus.model_validate(
        {"metrics": {"physical": 80, "energy": 80}}
    )
    plan_status = FinderPlanStatus()
    tracker = FinderStatusTracker(EmptyFinderPlaceTool())

    tracker.apply_activity(candidate, block, user_status, plan_status)

    assert plan_status.used_place_ids == ["museum"]
    assert plan_status.visited_tag_counts == {"culture": 1}
    assert plan_status.day_usage.activity_minutes == 60
    assert plan_status.trip_usage.place_count == 1
    assert user_status.metrics.physical == 75
    assert user_status.metrics.energy == 75
    assert user_status.location is not None
    assert user_status.location.place_id == "museum"

    tracker.rollback_activity(
        candidate,
        block,
        user_status,
        plan_status,
        restore_selected=False,
    )

    assert plan_status.used_place_ids == []
    assert plan_status.visited_tag_counts == {}
    assert plan_status.day_usage.activity_minutes == 0
    assert plan_status.trip_usage.place_count == 0
    assert user_status.metrics.physical == 80
    assert user_status.metrics.energy == 80


def test_status_tracker_break_increments_rest_and_updates_mood() -> None:
    block = DayBlock("lunch_break", "12:00-13:00", 60, False, kind="break")
    user_status = UserStatus.model_validate(
        {"metrics": {"energy": 60, "mental": 60}}
    )
    plan_status = FinderPlanStatus()
    tracker = FinderStatusTracker(EmptyFinderPlaceTool())

    tracker.apply_break(user_status, plan_status, block)

    assert plan_status.day_usage.rest_minutes == 60
    assert plan_status.trip_usage.rest_minutes == 60
    assert user_status.metrics.energy == 65
    assert user_status.metrics.mental == 63


def _item(name: str, time_window: str, duration: int) -> PlanItem:
    return PlanItem(
        itemId=name,
        name=name,
        timeWindow=time_window,
        placeType="attraction",
        timelineCategory="activity",
        durationMinutes=duration,
    )


def _leg(from_item: PlanItem, to_item: PlanItem, duration: int) -> PlanTransportLeg:
    return PlanTransportLeg(
        fromItemId=from_item.item_id,
        toItemId=to_item.item_id,
        fromPlace=from_item.name,
        toPlace=to_item.name,
        mode="walk",
        distanceMeters=100,
        estimatedDurationMinutes=duration,
    )


# ---------------------------------------------------------------------------
# Day-style selector
# ---------------------------------------------------------------------------


def _finder_place(
    name: str,
    place_type: str,
    *,
    place_group: str | None = None,
    tags: list[str] | None = None,
) -> FinderPlace:
    return FinderPlace(
        name=name,
        placeType=place_type,
        regionKey="vn,ha-noi",
        placeGroup=place_group,
        tags=tags or [],
    )


def test_day_style_selector_picks_anchor_when_majority_are_attractions() -> None:
    places = [
        _finder_place("Bảo tàng", "museum"),
        _finder_place("Công viên", "park"),
        _finder_place("Quán ăn", "restaurant"),
    ]

    decision = select_day_style(places)

    assert decision.style is DayStyle.anchor_day
    assert decision.anchor_count == 2
    assert decision.scattered_count == 0
    assert decision.total_considered == 2


def test_day_style_selector_picks_scattered_when_majority_are_short_stops() -> None:
    places = [
        _finder_place("Quán cafe", "cafe"),
        _finder_place("Tiệm bánh", "bakery"),
        _finder_place("Chợ", "marketplace"),
        _finder_place("Bảo tàng", "museum"),
    ]

    decision = select_day_style(places)

    assert decision.style is DayStyle.scattered_day
    assert decision.anchor_count == 1
    assert decision.scattered_count == 3


def test_day_style_selector_uses_area_profile_as_tiebreaker() -> None:
    places = [_finder_place("Quán cafe", "cafe"), _finder_place("Bảo tang", "museum")]
    distribution = {"shopping": 10, "entertainment": 5}

    decision = select_day_style(places, area_profile_distribution=distribution)

    assert decision.style is DayStyle.scattered_day


def test_day_style_selector_defaults_to_anchor_when_empty() -> None:
    decision = select_day_style(None)

    assert decision.style is DayStyle.anchor_day
    assert decision.total_considered == 0


def test_day_style_selector_excludes_meals_from_count() -> None:
    places = [
        _finder_place("Quán sáng", "restaurant"),
        _finder_place("Quán trưa", "restaurant"),
        _finder_place("Quán tối", "restaurant"),
    ]

    decision = select_day_style(places)

    assert decision.total_considered == 0
    assert decision.excluded_count == 3
    assert decision.style is DayStyle.anchor_day


def test_classify_place_unknown_category_returns_none() -> None:
    place = _finder_place("Khách sạn", "lodging", place_group="accommodation")

    assert classify_place(place) is None


# ---------------------------------------------------------------------------
# Day skeletons (anchor_day / scattered_day)
# ---------------------------------------------------------------------------


def _balanced_brief(day: int = 1) -> DayBrief:
    from app.modules.plans.domain.entities import DayBrief

    return DayBrief.model_validate(
        {
            "day": day,
            "theme": "explore",
            "targetArea": "vn,ha-noi",
            "pace": "balanced",
        }
    )


def test_build_anchor_day_emits_expected_layout() -> None:
    builder = DaySkeletonBuilder()
    user_status = UserStatus()

    skeleton = builder.build_anchor_day(_balanced_brief(), user_status)

    assert skeleton.strategy == "anchor_day"
    roles = [block.role for block in skeleton.blocks]
    assert roles[0] == "main_activity"
    assert any(role == "lunch_meal" for role in roles)
    assert any(role == "dinner_meal" for role in roles)
    assert any(role == "support_activity" for role in roles)
    assert any(role == "bonus_activity" for role in roles)
    assert any(role == "break_support_bonus" for role in roles)
    main_block = skeleton.blocks[0]
    assert main_block.duration_minutes == 180


def test_build_scattered_day_emits_expected_layout() -> None:
    builder = DaySkeletonBuilder()
    user_status = UserStatus()

    skeleton = builder.build_scattered_day(_balanced_brief(), user_status)

    assert skeleton.strategy == "scattered_day"
    roles = [block.role for block in skeleton.blocks]
    assert sum(role.startswith("stop_") for role in roles) >= 6
    assert any(role == "lunch_meal" for role in roles)
    assert any(role == "dinner_meal" for role in roles)
    durations = [b.duration_minutes for b in skeleton.blocks if b.role.startswith("stop_")]
    assert all(duration <= 60 for duration in durations)


def test_build_by_style_dispatches_to_correct_skeleton() -> None:
    builder = DaySkeletonBuilder()
    user_status = UserStatus()

    anchor = builder.build_by_style(DayStyle.anchor_day, _balanced_brief(), user_status)
    scattered = builder.build_by_style(
        DayStyle.scattered_day, _balanced_brief(), user_status
    )

    assert anchor.strategy == "anchor_day"
    assert scattered.strategy == "scattered_day"
