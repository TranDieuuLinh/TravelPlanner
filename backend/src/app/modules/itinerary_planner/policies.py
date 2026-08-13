from dataclasses import dataclass

from app.modules.itinerary_planner.contract import MealType


ITINERARY_START_MINUTE = 8 * 60
ITINERARY_END_MINUTE = 27 * 60


@dataclass(frozen=True, slots=True)
class MealPolicy:
    earliest_start: int
    latest_start: int
    duration_minutes: int
    target_start: int


MEAL_POLICIES: dict[MealType, MealPolicy] = {
    MealType.breakfast: MealPolicy(480, 510, 45, 480),
    MealType.lunch: MealPolicy(705, 795, 60, 750),
    MealType.dinner: MealPolicy(1065, 1170, 60, 1110),
}
