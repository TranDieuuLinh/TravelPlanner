from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SolverConfig:
    num_search_workers: int = 1
    pass1_timeout_seconds: float = 5
    pass2_timeout_seconds: float = 5
    pass3_timeout_seconds: float = 15
    random_seed: int = 42
    log_search_progress: bool = False


@dataclass(frozen=True, slots=True)
class ObjectiveWeights:
    policy_version: str = "itinerary-utility-v1"
    special_experience: int = 800
    preference_max: int = 600
    quality_max: int = 300
    time_fit: int = 200
    relationship: int = 250
    diversity_strong: int = 180
    diversity_medium: int = 90
    diversity_light: int = 30
    food_diversity: int = 100
    travel_minute: int = 3
    waiting_minute: int = 2
    meal_deviation_minute: int = 2
    late_minute: int = 4
    excess_stop: int = 100
    excess_active_minute: int = 1
    day_imbalance_minute: int = 1
    unknown_opening: int = 5


STRONG_TAGS = frozenset(
    {"museum", "shopping", "nightlife", "spa", "sightseeing", "hands_on"}
)
MEDIUM_TAGS = frozenset(
    {"indoor", "outdoor", "walking", "performance", "photography"}
)
LIGHT_TAGS = frozenset({"culture", "history", "nature", "local_experience"})
