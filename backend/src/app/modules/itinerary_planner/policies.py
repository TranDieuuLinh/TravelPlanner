from dataclasses import dataclass

from app.modules.itinerary_planner.contract import MealType

ITINERARY_START_MINUTE = 8 * 60
STANDARD_DAY_END_MINUTE = 23 * 60
OVERNIGHT_END_MINUTE = 27 * 60
MINIMUM_OVERNIGHT_REST_MINUTES = 9 * 60
ACCOMMODATION_RELOCATION_DISTANCE_METERS = 50_000
IDEAL_INTER_STOP_WAIT_MINUTES = 15
LIGHT_INTER_STOP_WAIT_MINUTES = 30
STRONG_INTER_STOP_WAIT_MINUTES = 60
MAX_INTER_STOP_WAIT_MINUTES = 150

LATE_NIGHT_TAGS = frozenset(
    {
        "bar",
        "beer",
        "cocktail",
        "drinking",
        "karaoke",
        "late_night",
        "live_music",
        "nightlife",
        "pub",
    }
)


@dataclass(frozen=True, slots=True)
class MealPolicy:
    earliest_start: int
    latest_start: int
    duration_minutes: int
    target_start: int


MEAL_POLICIES: dict[MealType, MealPolicy] = {
    MealType.breakfast: MealPolicy(480, 600, 45, 480),
    MealType.lunch: MealPolicy(705, 795, 60, 750),
    MealType.dinner: MealPolicy(1065, 1170, 60, 1110),
}

MINIMUM_MEAL_START_GAPS: dict[tuple[MealType, MealType], int] = {
    (MealType.breakfast, MealType.lunch): 180,
    (MealType.lunch, MealType.dinner): 300,
}
