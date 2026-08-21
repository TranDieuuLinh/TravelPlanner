from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepairStop:
    internal_id: str
    duration_minutes: int
    original_start: int
    start_ranges: tuple[tuple[int, int], ...]
    meal_type: str | None = None


@dataclass(frozen=True, slots=True)
class RepairAnchors:
    accommodation_id: str | None = None
    require_start: bool = False
    require_return: bool = False


@dataclass(frozen=True, slots=True)
class RepairedStop:
    internal_id: str
    start_minute: int
    end_minute: int


@dataclass(frozen=True, slots=True)
class DayScheduleRepair:
    strategy: str
    stops: tuple[RepairedStop, ...]

