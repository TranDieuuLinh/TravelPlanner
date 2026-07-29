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
    kind: str = "activity"


@dataclass(frozen=True)
class DaySkeleton:
    strategy: str
    blocks: tuple[DayBlock, ...]


class DaySkeletonBuilder:
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
