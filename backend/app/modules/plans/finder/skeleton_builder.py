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
        if self._needs_recovery(user_status):
            return DaySkeleton(
                strategy="recovery",
                blocks=(
                    DayBlock("late_main_activity", "10:00-11:30", 90, True),
                    DayBlock("lunch_meal", "11:45-12:45", 60, False, kind="meal"),
                    DayBlock("recovery_break", "13:00-14:30", 90, False, kind="break"),
                    DayBlock("light_support_activity", "15:00-16:30", 90, True),
                ),
            )
        if self._prefers_indoor(intent_constraints or []):
            return DaySkeleton(
                strategy="indoor_safe",
                blocks=(
                    DayBlock("main_activity", "09:30-11:30", 120, True),
                    DayBlock("lunch_meal", "11:45-12:45", 60, False, kind="meal"),
                    DayBlock("support_activity", "13:15-15:15", 120, True),
                    DayBlock("indoor_break", "15:15-16:00", 45, False, kind="break"),
                    DayBlock("bonus_activity", "16:15-17:45", 90, True, optional=True),
                ),
            )
        if pace == TravelPace.relaxed:
            return DaySkeleton(
                strategy="relaxed",
                blocks=(
                    DayBlock("main_activity", "09:00-11:00", 120, True),
                    DayBlock("lunch_meal", "11:30-12:30", 60, False, kind="meal"),
                    DayBlock("break_main_support", "12:30-14:00", 90, False, kind="break"),
                    DayBlock("support_activity", "14:00-16:00", 120, True),
                ),
            )
        if pace == TravelPace.packed:
            return DaySkeleton(
                strategy="multi_stop",
                blocks=(
                    DayBlock("main_activity", "08:30-10:00", 90, True),
                    DayBlock("support_activity_1", "10:15-11:45", 90, True),
                    DayBlock("lunch_meal", "11:45-12:45", 60, False, kind="meal"),
                    DayBlock("support_activity_2", "13:00-14:30", 90, True),
                    DayBlock("break_2", "14:30-15:15", 45, False, kind="break"),
                    DayBlock("support_activity_3", "15:30-17:00", 90, True),
                    DayBlock(
                        "bonus_activity",
                        "17:30-19:00",
                        90,
                        True,
                        optional=True,
                    ),
                ),
            )
        return DaySkeleton(
            strategy="anchor_led",
            blocks=(
                DayBlock("main_activity", "09:00-11:00", 120, True),
                DayBlock("lunch_meal", "11:30-12:30", 60, False, kind="meal"),
                DayBlock("support_activity", "13:00-15:30", 150, True),
                DayBlock("break_support_bonus", "15:30-16:30", 60, False, kind="break"),
                DayBlock(
                    "bonus_activity",
                    "17:00-19:00",
                    120,
                    True,
                    optional=True,
                ),
            ),
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
