from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from app.modules.plans.domain.entities import DayBrief, UserStatus
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.finder.time_windows import (
    format_clock,
    format_clock_window,
    parse_clock_minutes,
)

if TYPE_CHECKING:
    from app.modules.plans.finder.area_survey import AreaProfile
    from app.modules.plans.finder.day_style_selector import DayStyle


@dataclass(frozen=True)
class DayBlock:
    role: str
    time_window: str
    duration_minutes: int
    activity: bool
    optional: bool = False
    preferred_ref: str | None = None
    kind: str = "activity"
    candidate_category: str | None = None
    earliest_start: str | None = None
    latest_end: str | None = None
    min_duration_minutes: int | None = None
    goal: str | None = None
    preferred_experiences: tuple[str, ...] = ()


@dataclass(frozen=True)
class DaySkeleton:
    strategy: str
    blocks: tuple[DayBlock, ...]


class DaySkeletonBuilder:
    _MIN_ACTIVITY_COUNT = {
        TravelPace.relaxed: 2,
        TravelPace.balanced: 3,
        TravelPace.packed: 4,
    }
    _SUPPLEMENTAL_WINDOWS = (
        ("09:30-11:00", 90),
        ("13:30-15:00", 90),
        ("15:30-17:00", 90),
        ("19:00-20:30", 90),
        ("11:15-12:45", 90),
    )
    _SOURCE_START_MINUTES = {
        "breakfast": 8 * 60,
        "early morning": 7 * 60,
        "morning": 9 * 60,
        "late morning": 10 * 60 + 30,
        "before lunch": 11 * 60,
        "lunch": 12 * 60,
        "early afternoon": 13 * 60,
        "afternoon": 14 * 60,
        "late afternoon": 16 * 60,
        "dinner": 18 * 60,
        "evening": 18 * 60,
        "after dinner": 19 * 60 + 30,
        "night": 20 * 60,
        "nightlife": 21 * 60,
    }
    _SOURCE_DEFAULT_DURATIONS = {
        "breakfast": 45,
        "early morning": 45,
        "morning": 45,
        "late morning": 45,
        "before lunch": 120,
        "lunch": 75,
        "early afternoon": 60,
        "afternoon": 75,
        "late afternoon": 60,
        "dinner": 60,
        "evening": 60,
        "after dinner": 60,
        "night": 75,
        "nightlife": 90,
    }

    def apply_flexible_needs(
        self,
        skeleton: DaySkeleton,
        brief: DayBrief,
    ) -> DaySkeleton:
        """Overlay soft windows/goals while preserving legacy skeleton roles."""

        activity_needs = {need.role: need for need in brief.activity_needs}
        meal_needs = {need.role: need for need in brief.meal_needs}
        day_start = brief.day_window.earliest_start
        day_end = brief.day_window.latest_end
        lunch = meal_needs.get("lunch")
        dinner = meal_needs.get("dinner")
        lunch_start = lunch.earliest_start if lunch else "11:30"
        lunch_end = lunch.latest_end if lunch else "13:30"
        dinner_start = dinner.earliest_start if dinner else "17:30"
        dinner_end = dinner.latest_end if dinner else "20:00"

        flexible_blocks: list[DayBlock] = []
        for block in skeleton.blocks:
            # Source itineraries carry ordering/time evidence of their own.
            # Keep those explicit slots intact; flexible needs govern only the
            # Finder-generated day skeleton.
            if block.role.startswith(("stop_", "url_stop_")):
                flexible_blocks.append(block)
                continue
            if block.kind == "meal":
                meal_role = "lunch" if "lunch" in block.role else "dinner"
                need = meal_needs.get(meal_role)
                flexible_blocks.append(
                    replace(
                        block,
                        earliest_start=(need.earliest_start if need else lunch_start if meal_role == "lunch" else dinner_start),
                        latest_end=(need.latest_end if need else lunch_end if meal_role == "lunch" else dinner_end),
                        min_duration_minutes=(need.min_duration_minutes if need else 45),
                        duration_minutes=(need.max_duration_minutes if need else block.duration_minutes),
                    )
                )
                continue
            if not block.activity:
                flexible_blocks.append(block)
                continue

            if "main" in block.role:
                need_role = "main"
            elif "bonus" in block.role:
                need_role = "bonus"
            else:
                need_role = "support"
            need = activity_needs.get(need_role)
            if need_role == "main":
                earliest, latest = day_start, lunch_start
            elif need_role == "support":
                earliest, latest = lunch_end, dinner_start
            else:
                earliest, latest = dinner_end, day_end
            flexible_blocks.append(
                replace(
                    block,
                    earliest_start=earliest,
                    latest_end=latest,
                    min_duration_minutes=(need.min_duration_minutes if need else 30),
                    duration_minutes=(need.max_duration_minutes if need else block.duration_minutes),
                    optional=(not need.required if need else block.optional),
                    goal=(need.goal if need else None),
                    preferred_experiences=(tuple(need.preferred_experiences) if need else ()),
                )
            )
        return DaySkeleton(strategy=skeleton.strategy, blocks=tuple(flexible_blocks))

    def build(
        self,
        brief: DayBrief,
        user_status: UserStatus,
        intent_constraints: list[str] | None = None,
        area_profile: AreaProfile | None = None,
    ) -> DaySkeleton:
        pace = self._effective_pace(brief.pace, user_status, area_profile)
        start_min = self._extract_start_minutes(
            user_status,
            default_minutes=self._default_start_minutes(
                pace,
                user_status,
                intent_constraints,
                area_profile,
            ),
            area_profile=area_profile,
        )

        if self._needs_recovery(user_status):
            cur = start_min
            b1 = DayBlock("late_main_activity", self._clock_window(cur, 90), 90, True)
            cur += 105
            lunch_start = max(12 * 60, cur)
            b2 = DayBlock(
                "lunch_meal",
                self._clock_window(lunch_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = lunch_start + 60
            b3 = DayBlock("recovery_break", self._clock_window(cur, 90), 90, False, kind="break")
            cur += 90
            b4 = DayBlock("light_support_activity", self._clock_window(cur, 90), 90, True)
            cur += 90
            dinner_start = max(18 * 60, min(20 * 60, cur))
            b5 = DayBlock(
                "dinner_meal",
                self._clock_window(dinner_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = dinner_start + 60
            blocks = [b1, b2, b3, b4, b5]
            if cur + 30 < 23 * 60:
                blocks.append(
                    DayBlock("group_social_activity", self._clock_window(cur + 30, 90), 90, False, optional=True, kind="social_activity")
                )
            return DaySkeleton(strategy="recovery", blocks=tuple(blocks))

        if self._prefers_indoor(intent_constraints or []):
            cur = start_min
            b1 = DayBlock("main_activity", self._clock_window(cur, 120), 120, True)
            cur += 120
            lunch_start = max(12 * 60, min(13 * 60, cur))
            b2 = DayBlock(
                "lunch_meal",
                self._clock_window(lunch_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = lunch_start + 60 + 15
            b3 = DayBlock("support_activity", self._clock_window(cur, 120), 120, True)
            cur += 120
            b4 = DayBlock("indoor_break", self._clock_window(cur, 45), 45, False, kind="break")
            cur += 45
            dinner_start = max(18 * 60, min(20 * 60, cur))
            b5 = DayBlock(
                "dinner_meal",
                self._clock_window(dinner_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = dinner_start + 60 + 15
            b6 = DayBlock("bonus_activity", self._clock_window(cur, 75), 75, True, optional=True)
            cur += 75 + 15
            blocks = [b1, b2, b3, b4, b5, b6]
            if cur < 23 * 60:
                blocks.append(
                    DayBlock("group_social_activity", self._clock_window(cur, 75), 75, False, optional=True, kind="social_activity")
                )
            return DaySkeleton(strategy="indoor_safe", blocks=tuple(blocks))

        if pace == TravelPace.relaxed:
            cur = start_min
            b1 = DayBlock("main_activity", self._clock_window(cur, 120), 120, True)
            cur += 120
            lunch_start = max(12 * 60, min(13 * 60, cur))
            b2 = DayBlock(
                "lunch_meal",
                self._clock_window(lunch_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = lunch_start + 60
            b3 = DayBlock("break_main_support", self._clock_window(cur, 90), 90, False, kind="break")
            cur += 90
            b4 = DayBlock("support_activity", self._clock_window(cur, 120), 120, True)
            cur += 120
            dinner_start = max(18 * 60, min(20 * 60, cur))
            b5 = DayBlock(
                "dinner_meal",
                self._clock_window(dinner_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = dinner_start + 60
            blocks = [b1, b2, b3, b4, b5]
            if cur + 30 < 23 * 60:
                blocks.append(
                    DayBlock("group_social_activity", self._clock_window(cur + 30, 90), 90, False, optional=True, kind="social_activity")
                )
            return DaySkeleton(strategy="relaxed", blocks=tuple(blocks))

        if pace == TravelPace.packed:
            cur = start_min
            b1 = DayBlock("main_activity", self._clock_window(cur, 90), 90, True)
            cur += 90 + 15
            b2 = DayBlock("support_activity_1", self._clock_window(cur, 90), 90, True)
            cur += 90
            lunch_start = max(12 * 60, min(13 * 60, cur))
            b3 = DayBlock(
                "lunch_meal",
                self._clock_window(lunch_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = lunch_start + 60 + 15
            b4 = DayBlock("support_activity_2", self._clock_window(cur, 90), 90, True)
            cur += 90
            b5 = DayBlock("break_2", self._clock_window(cur, 45), 45, False, kind="break")
            cur += 45 + 15
            b6 = DayBlock("support_activity_3", self._clock_window(cur, 90), 90, True)
            cur += 90
            dinner_start = max(18 * 60, min(20 * 60, cur))
            b7 = DayBlock(
                "dinner_meal",
                self._clock_window(dinner_start, 60),
                60,
                False,
                kind="meal",
                candidate_category="food_drink",
            )
            cur = dinner_start + 60 + 30
            b8 = DayBlock("bonus_activity", self._clock_window(cur, 90), 90, True, optional=True)
            cur += 90 + 15
            blocks = [b1, b2, b3, b4, b5, b6, b7, b8]
            if cur < 23 * 60:
                blocks.append(
                    DayBlock("group_social_activity", self._clock_window(cur, 75), 75, False, optional=True, kind="social_activity")
                )
            return DaySkeleton(strategy="multi_stop", blocks=tuple(blocks))

        cur = start_min
        b1 = DayBlock("main_activity", self._clock_window(cur, 120), 120, True)
        cur += 120
        lunch_start = max(12 * 60, min(13 * 60, cur))
        b2 = DayBlock(
            "lunch_meal",
            self._clock_window(lunch_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        )
        cur = lunch_start + 60 + 30
        b3 = DayBlock("support_activity", self._clock_window(cur, 150), 150, True)
        cur += 150
        b4 = DayBlock("break_support_bonus", self._clock_window(cur, 60), 60, False, kind="break")
        cur += 60
        dinner_start = max(18 * 60, min(20 * 60, cur))
        b5 = DayBlock(
            "dinner_meal",
            self._clock_window(dinner_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        )
        cur = dinner_start + 60 + 15
        b6 = DayBlock("bonus_activity", self._clock_window(cur, 120), 120, True, optional=True)
        cur += 120 + 15
        blocks = [b1, b2, b3, b4, b5, b6]
        if cur < 23 * 60:
            blocks.append(
                DayBlock("group_social_activity", self._clock_window(cur, 75), 75, False, optional=True, kind="social_activity")
            )
        return DaySkeleton(
            strategy="anchor_led",
            blocks=tuple(blocks),
        )

    def _default_start_minutes(
        self,
        pace: TravelPace,
        user_status: UserStatus,
        intent_constraints: list[str] | None,
        area_profile: AreaProfile | None = None,
    ) -> int:
        if self._needs_recovery(user_status):
            return 9 * 60 + 30
        if self._prefers_indoor(intent_constraints or []):
            return 8 * 60 + 30
        if pace == TravelPace.relaxed:
            return 8 * 60 + 30
        if pace == TravelPace.packed:
            return 7 * 60 + 30
        # Adjust start time based on area typical hours
        if area_profile is not None:
            if area_profile.typical_hours == "morning_focused":
                return 8 * 60  # Start at the earliest commonly reported opening time
            elif area_profile.typical_hours == "evening_focused":
                return 9 * 60  # Later start for evening areas
        return 8 * 60

    def _extract_start_minutes(
        self,
        user_status: UserStatus,
        default_minutes: int,
        area_profile: AreaProfile | None = None,
    ) -> int:
        if not user_status.available_at:
            return default_minutes
        parsed = parse_clock_minutes(user_status.available_at)
        return default_minutes if parsed is None else parsed

    def _clock_window(self, start: int, duration: int) -> str:
        return format_clock_window(start, duration, bound_to_day=True)

    def build_anchor_day(
        self,
        brief: DayBrief,
        user_status: UserStatus,
        *,
        intent_constraints: list[str] | None = None,
        area_profile: AreaProfile | None = None,
    ) -> DaySkeleton:
        """Day skeleton for "long-anchor" days (museum / park / complex).

        Layout::

            08:30-11:30  main_activity           180'
            12:00-13:00  lunch_meal               60'
            13:30-15:00  support_activity         90'
            15:30-16:30  break_support_bonus      60'
            18:00-19:00  dinner_meal              60'
            19:30-21:00  bonus_activity           90'

        Strategy name: ``"anchor_day"``. Role names are kept aligned with
        the previous ``anchor_led`` strategy so downstream consumers do not
        need to special-case the new day shapes.
        """

        pace = self._effective_pace(brief.pace, user_status, area_profile)
        start_min = self._extract_start_minutes(
            user_status,
            default_minutes=self._default_start_minutes(
                pace,
                user_status,
                intent_constraints,
                area_profile,
            ),
            area_profile=area_profile,
        )
        if not user_status.available_at:
            start_min = max(start_min, 9 * 60)

        cur = start_min
        b1 = DayBlock("main_activity", self._clock_window(cur, 180), 180, True)
        cur += 180
        lunch_start = max(12 * 60, min(13 * 60, cur))
        b2 = DayBlock(
            "lunch_meal",
            self._clock_window(lunch_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        )
        cur = lunch_start + 60 + 30
        b3 = DayBlock("support_activity", self._clock_window(cur, 120), 120, True)
        cur += 120 + 30
        b4 = DayBlock(
            "break_support_bonus", self._clock_window(cur, 60), 60, False, kind="break"
        )
        cur += 60
        dinner_start = max(18 * 60, min(20 * 60, cur))
        b5 = DayBlock(
            "dinner_meal",
            self._clock_window(dinner_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        )
        cur = dinner_start + 60 + 30
        b6 = DayBlock("bonus_activity", self._clock_window(cur, 90), 90, True, optional=True)
        cur += 90
        blocks = [b1, b2, b3, b4, b5, b6]
        if cur + 30 < 23 * 60:
            blocks.append(
                DayBlock(
                    "group_social_activity",
                    self._clock_window(cur + 30, 90),
                    90,
                    False,
                    optional=True,
                    kind="social_activity",
                )
            )
        return DaySkeleton(strategy="anchor_day", blocks=tuple(blocks))

    def build_scattered_day(
        self,
        brief: DayBrief,
        user_status: UserStatus,
        *,
        intent_constraints: list[str] | None = None,
        area_profile: AreaProfile | None = None,
    ) -> DaySkeleton:
        """Build a short-stop day whose density follows the effective pace.

        Meals are separate from the activity capacity: relaxed, balanced and
        packed days receive two, three and five short stops respectively.
        """

        pace = self._effective_pace(brief.pace, user_status, area_profile)
        start_min = self._extract_start_minutes(
            user_status,
            default_minutes=self._default_start_minutes(
                pace,
                user_status,
                intent_constraints,
                area_profile,
            ),
            area_profile=area_profile,
        )

        stop_count = {
            TravelPace.relaxed: 2,
            TravelPace.balanced: 3,
            TravelPace.packed: 5,
        }[pace]
        morning_stop_count = min(3, (stop_count + 1) // 2)
        blocks: list[DayBlock] = []
        cur = start_min
        next_stop_number = 1
        for _ in range(morning_stop_count):
            duration = 45 if next_stop_number <= 2 else 60
            blocks.append(
                DayBlock(
                    f"stop_{next_stop_number}",
                    self._clock_window(cur, duration),
                    duration,
                    True,
                )
            )
            next_stop_number += 1
            cur += duration + 15

        lunch_start = max(12 * 60, min(13 * 60, cur))
        blocks.append(DayBlock(
            "lunch_meal",
            self._clock_window(lunch_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        ))
        cur = lunch_start + 60 + 45
        while next_stop_number <= stop_count:
            duration = 45 if next_stop_number < stop_count else 60
            blocks.append(
                DayBlock(
                    f"stop_{next_stop_number}",
                    self._clock_window(cur, duration),
                    duration,
                    True,
                )
            )
            next_stop_number += 1
            cur += duration + 15

        dinner_start = max(18 * 60, min(20 * 60, cur))
        blocks.append(DayBlock(
            "dinner_meal",
            self._clock_window(dinner_start, 60),
            60,
            False,
            kind="meal",
            candidate_category="food_drink",
        ))
        cur = dinner_start + 60
        if cur + 105 < 23 * 60:
            blocks.append(
                DayBlock(
                    "group_social_activity",
                    self._clock_window(cur + 30, 75),
                    75,
                    False,
                    optional=True,
                    kind="social_activity",
                )
            )
        return DaySkeleton(strategy="scattered_day", blocks=tuple(blocks))

    def build_by_style(
        self,
        style: "DayStyle",
        brief: DayBrief,
        user_status: UserStatus,
        *,
        intent_constraints: list[str] | None = None,
        area_profile: AreaProfile | None = None,
    ) -> DaySkeleton:
        """Dispatch to :meth:`build_anchor_day` or :meth:`build_scattered_day`."""

        from app.modules.plans.finder.day_style_selector import DayStyle

        if style == DayStyle.scattered_day:
            return self.build_scattered_day(
                brief,
                user_status,
                intent_constraints=intent_constraints,
                area_profile=area_profile,
            )
        return self.build_anchor_day(
            brief,
            user_status,
            intent_constraints=intent_constraints,
            area_profile=area_profile,
        )

    def build_source_itinerary(
        self,
        brief: DayBrief,
        selected_places: list[SelectedPlaceContext],
        *,
        supplement_sparse_day: bool = False,
    ) -> DaySkeleton:
        ordered = sorted(
            selected_places,
            key=lambda place: (place.source_order or 10_000, place.name.casefold()),
        )
        cursor = 8 * 60
        blocks: list[DayBlock] = []
        for place in ordered:
            duration = (
                place.source_duration_minutes
                or self._source_default_duration(place.source_time_hint)
            )
            hinted_start = self._source_start(place.source_time_hint)
            start = max(cursor, hinted_start) if hinted_start is not None else cursor
            end = start + duration
            blocks.append(
                DayBlock(
                    role=f"url_stop_{place.source_order or len(blocks) + 1}",
                    time_window=format_clock_window(start, duration, bound_to_day=True),
                    duration_minutes=duration,
                    activity=True,
                    preferred_ref=place.stable_ref,
                )
            )
            cursor = end + 10
        if not supplement_sparse_day:
            return DaySkeleton(
                strategy="source_itinerary",
                blocks=tuple(blocks),
            )

        target_count = self.minimum_activity_count(brief.pace)
        missing_count = max(0, target_count - len(blocks))
        source_intervals = [
            self._window_interval(block.time_window)
            for block in blocks
        ]
        supplemental_blocks: list[DayBlock] = []
        for time_window, duration in self._SUPPLEMENTAL_WINDOWS:
            if len(supplemental_blocks) >= missing_count:
                break
            interval = self._window_interval(time_window)
            if any(
                self._intervals_overlap(interval, source_interval, buffer=10)
                for source_interval in source_intervals
            ):
                continue
            supplemental_blocks.append(
                DayBlock(
                    role=f"finder_support_{len(supplemental_blocks) + 1}",
                    time_window=time_window,
                    duration_minutes=duration,
                    activity=True,
                )
            )

        combined = sorted(
            [*blocks, *supplemental_blocks],
            key=lambda block: self._window_interval(block.time_window)[0],
        )
        return DaySkeleton(
            strategy=(
                "source_itinerary_supplemented"
                if supplemental_blocks
                else "source_itinerary"
            ),
            blocks=tuple(combined),
        )

    def minimum_activity_count(self, pace: TravelPace) -> int:
        return self._MIN_ACTIVITY_COUNT[pace]

    def _window_interval(self, time_window: str) -> tuple[int, int]:
        start, end = time_window.split("-", maxsplit=1)
        return parse_clock_minutes(start) or 0, parse_clock_minutes(end) or 0

    def _intervals_overlap(
        self,
        left: tuple[int, int],
        right: tuple[int, int],
        *,
        buffer: int = 0,
    ) -> bool:
        return left[0] < right[1] + buffer and right[0] < left[1] + buffer

    def _source_start(self, hint: str | None) -> int | None:
        if not hint:
            return None
        normalized = hint.strip().casefold().replace("_", " ")
        exact = self._SOURCE_START_MINUTES.get(normalized)
        if exact is not None:
            return exact
        for phrase, minutes in sorted(
            self._SOURCE_START_MINUTES.items(),
            key=lambda item: -len(item[0]),
        ):
            if phrase in normalized:
                return minutes
        return None

    def _source_default_duration(self, hint: str | None) -> int:
        if not hint:
            return 60
        normalized = hint.strip().casefold().replace("_", " ")
        for phrase, duration in sorted(
            self._SOURCE_DEFAULT_DURATIONS.items(),
            key=lambda item: -len(item[0]),
        ):
            if phrase == normalized or phrase in normalized:
                return duration
        return 60

    def _clock(self, minutes: int) -> str:
        return format_clock(minutes, bound_to_day=True)

    def _needs_recovery(self, user_status: UserStatus) -> bool:
        known_capacity = [
            value
            for value in (
                user_status.metrics.physical,
                user_status.metrics.energy,
                user_status.metrics.mental,
            )
            if value is not None
        ]
        return bool(known_capacity and min(known_capacity) <= 30)

    def _prefers_indoor(self, intent_constraints: list[str]) -> bool:
        constraints = {
            constraint.strip().casefold().replace("-", "_").replace(" ", "_")
            for constraint in intent_constraints
        }
        return bool(
            constraints.intersection(
                {
                    "avoid_outdoor",
                    "bad_weather",
                    "rain",
                    "indoor_only",
                }
            )
        )

    def _effective_pace(
        self,
        requested_pace: TravelPace,
        user_status: UserStatus,
        area_profile: AreaProfile | None = None,
    ) -> TravelPace:
        known_capacity = [
            value
            for value in (
                user_status.metrics.physical,
                user_status.metrics.energy,
            )
            if value is not None
        ]
        if known_capacity and min(known_capacity) <= 40:
            return TravelPace.relaxed
        # Adjust pace based on area density - sparse areas need slower pace
        if area_profile is not None:
            if area_profile.estimated_walkability == "low" and requested_pace == TravelPace.packed:
                # Don't pack too tight in low walkability areas
                return TravelPace.balanced
        return requested_pace
