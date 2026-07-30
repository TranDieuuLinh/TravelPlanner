from __future__ import annotations

from dataclasses import dataclass

from app.modules.plans.domain.entities import DayBrief, UserStatus
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext


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

    def build(
        self,
        brief: DayBrief,
        user_status: UserStatus,
        intent_constraints: list[str] | None = None,
    ) -> DaySkeleton:
        pace = self._effective_pace(brief.pace, user_status)
        start_min = self._extract_start_minutes(user_status, default_minutes=self._default_start_minutes(pace, user_status, intent_constraints))

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
    ) -> int:
        if self._needs_recovery(user_status):
            return 9 * 60 + 30
        if self._prefers_indoor(intent_constraints or []):
            return 8 * 60 + 30
        if pace == TravelPace.relaxed:
            return 8 * 60 + 30
        if pace == TravelPace.packed:
            return 7 * 60 + 30
        return 8 * 60

    def _extract_start_minutes(self, user_status: UserStatus, default_minutes: int) -> int:
        if not user_status.available_at:
            return default_minutes
        import re
        match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)", user_status.available_at)
        if match is None:
            return default_minutes
        return int(match.group(1)) * 60 + int(match.group(2))

    def _clock_window(self, start: int, duration: int) -> str:
        return f"{self._clock(start)}-{self._clock(start + duration)}"

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
                    time_window=f"{self._clock(start)}-{self._clock(end)}",
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
        return self._clock_minutes(start), self._clock_minutes(end)

    def _clock_minutes(self, value: str) -> int:
        hours, minutes = value.split(":", maxsplit=1)
        return int(hours) * 60 + int(minutes)

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
        bounded = min(minutes, 23 * 60 + 59)
        return f"{bounded // 60:02d}:{bounded % 60:02d}"

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
        return requested_pace
