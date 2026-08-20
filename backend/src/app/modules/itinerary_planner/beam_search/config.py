from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BeamSearchWeights:
    quality: int = 35
    preference: int = 15
    style: int = 10
    time_fit: int = 15
    travel: int = 15
    budget: int = 10
    diversity: int = 5
    relationship: int = 5
    restaurant_coverage: int = 18
    travelplace_quality_multiplier: float = 1.50
    restaurant_quality_multiplier: float = 1.10
    drink_dessert_quality_multiplier: float = 0.95
    entertainment_quality_multiplier: float = 0.85
    travelplace_day_bonus: int = 12
    travelplace_final_weight: int = 10


@dataclass(frozen=True, slots=True)
class BeamSearchConfig:
    beam_width: int = 32
    # Keep a wider per-day candidate pool so global day-combination search can
    # backtrack when the locally best day consumes a travel place needed later.
    combination_beam_width: int = 32
    max_stops_per_day: int = 16
    # A Beam transition may wait for a later opening window, but a long idle
    # gap is not considered a useful connection.
    max_wait_minutes: int = 60
    # Beam may consider three leisure-food stops so diversity can choose
    # 2 drink/dessert + 1 entertainment over 3 drink/dessert.
    max_drink_desserts_per_day: int = 3
    target_restaurant_count: int = 3
    restaurant_fill_windows: tuple[tuple[int, int], ...] = (
        (11 * 60, 13 * 60),
        (18 * 60, 20 * 60),
    )
    long_distance_rating_min: float = 3.0
    review_quantile: float = 0.5
    # An explicit value overrides the adaptive whole-search budget.  The
    # deadline covers every day and every global backtracking branch; it is
    # never reset for an individual _search_day invocation.
    time_limit_seconds: float | None = None
    one_day_time_limit_seconds: float = 5.0
    multi_day_time_limit_seconds: float = 8.0
    long_trip_time_limit_seconds: float = 12.0
    deadline_check_interval: int = 16
    policy_version: str = "beam-search-v1"
    weights: BeamSearchWeights = BeamSearchWeights()

    def resolved_time_limit_seconds(self, days: int) -> float:
        if self.time_limit_seconds is not None:
            return max(0.0, self.time_limit_seconds)
        if days == 1:
            return self.one_day_time_limit_seconds
        if days <= 3:
            return self.multi_day_time_limit_seconds
        return self.long_trip_time_limit_seconds
