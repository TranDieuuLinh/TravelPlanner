from __future__ import annotations

from dataclasses import dataclass

from app.modules.itinerary_planner.contract import MealType
from app.modules.itinerary_planner.optimizer.result import ScheduledStop


@dataclass(frozen=True, slots=True)
class DaySearchState:
    stops: tuple[ScheduledStop, ...] = ()
    selected_ids: frozenset[str] = frozenset()
    priority_ids: frozenset[str] = frozenset()
    last_id: str | None = None
    end_minute: int = 480
    meal_starts: tuple[tuple[MealType, int], ...] = ()
    score: float = 0.0
    cost: int = 0
    restaurant_count: int = 0
    travelplace_count: int = 0
    drink_dessert_count: int = 0
    entertainment_count: int = 0


@dataclass(frozen=True, slots=True)
class PlanSearchState:
    days: tuple[tuple[ScheduledStop, ...], ...] = ()
    selected_ids: frozenset[str] = frozenset()
    priority_ids: frozenset[str] = frozenset()
    score: float = 0.0
    cost: int = 0
    restaurant_count: int = 0
    travelplace_count: int = 0
    drink_dessert_count: int = 0
    entertainment_count: int = 0
    diversity_count: int = 0
