from __future__ import annotations

from dataclasses import dataclass

from app.modules.plans.domain.entities import DayBrief, UserStatus
from app.modules.plans.domain.enums import TravelPace


@dataclass(frozen=True)
class DayBlock:
    role: str
    time_window: str
    duration_minutes: int
    activity: bool
    optional: bool = False


@dataclass(frozen=True)
class DaySkeleton:
    strategy: str
    blocks: tuple[DayBlock, ...]


class DaySkeletonBuilder:
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
