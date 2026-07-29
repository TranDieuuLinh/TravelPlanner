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


@dataclass(frozen=True)
class DaySkeleton:
    strategy: str
    blocks: tuple[DayBlock, ...]


class DaySkeletonBuilder:
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
    ) -> DaySkeleton:
        pace = self._effective_pace(brief.pace, user_status)
        if pace == TravelPace.relaxed:
            return DaySkeleton(
                strategy="relaxed",
                blocks=(
                    DayBlock("main_activity", "09:00-11:00", 120, True),
                    DayBlock("break_main_support", "11:00-12:00", 60, False),
                    DayBlock("support_activity", "14:00-16:00", 120, True),
                ),
            )
        if pace == TravelPace.packed:
            return DaySkeleton(
                strategy="multi_stop",
                blocks=(
                    DayBlock("main_activity", "08:30-10:00", 90, True),
                    DayBlock("support_activity_1", "10:15-11:45", 90, True),
                    DayBlock("break_1", "11:45-12:45", 60, False),
                    DayBlock("support_activity_2", "13:00-14:30", 90, True),
                    DayBlock("break_2", "14:30-15:15", 45, False),
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
                DayBlock("break_main_support", "11:00-12:00", 60, False),
                DayBlock("support_activity", "13:00-15:30", 150, True),
                DayBlock("break_support_bonus", "15:30-16:30", 60, False),
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
        return DaySkeleton(strategy="source_itinerary", blocks=tuple(blocks))

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
