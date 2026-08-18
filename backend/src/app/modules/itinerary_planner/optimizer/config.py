from dataclasses import dataclass

from app.modules.itinerary_planner.policies import MAX_INTER_STOP_WAIT_MINUTES


@dataclass(frozen=True, slots=True)
class SolverConfig:
    num_search_workers: int = 1
    priority_timeout_seconds: float | None = None
    utility_timeout_seconds: float | None = None
    utility_relative_gap_limit: float = 0.05
    utility_parallel_workers: int = 3
    max_utility_no_improvement_rounds: int = 1
    random_seed: int = 42
    log_search_progress: bool = False
    max_inter_stop_wait_minutes: int | None = MAX_INTER_STOP_WAIT_MINUTES


@dataclass(frozen=True, slots=True)
class ObjectiveWeights:
    policy_version: str = "itinerary-utility-v16-evening-special-first"
    activity_coverage: int = 350
    special_experience: int = 4_000
    preference_max: int = 600
    style_max: int = 400
    quality_max: int = 300
    popularity_max: int = 250
    time_fit: int = 200
    relationship: int = 250
    diversity_strong: int = 180
    diversity_medium: int = 90
    diversity_light: int = 30
    consecutive_diversity_max: int = 300
    food_diversity: int = 100
    low_quality_food: int = 3_000
    low_confidence_generic_place: int = 1_500
    travel_minute: int = 3
    accommodation_long_transfer: int = 5_000
    accommodation_price_10k: int = 1
    waiting_minute: int = 2
    meal_deviation_minute: int = 2
    late_minute: int = 4
    excess_stop: int = 800
    excess_active_minute: int = 1
    day_imbalance_minute: int = 1
    unknown_opening: int = 5
    source_mix_deviation: int = 2_000
    daytime_entertainment_excess: int = 6_000
    evening_special_experience: int = 9_000
    evening_entertainment_fallback: int = 7_000
    evening_entertainment_special_conflict: int = 6_000
    special_place_shortfall: int = 10_000
    popular_place_shortfall: int = 6_000
    budget_overage_10k: int = 500


STRONG_TAGS = frozenset(
    {
        "museum",
        "shopping",
        "nightlife",
        "spa",
        "sightseeing",
        "hands_on",
        "tâm_linh",
        "mua_sắm",
        "nghỉ_dưỡng",
        "thư_giãn",
        "rượu_bia",
        "drunk",
        "18",
        "quân_sự",
        "thể_thao",
    }
)
MEDIUM_TAGS = frozenset(
    {
        "indoor",
        "outdoor",
        "walking",
        "performance",
        "photography",
        "kiến_trúc",
        "chụp_ảnh",
        "núi",
        "biển",
        "di_tích",
        "gia_đình",
        "sang_trọng",
        "sinh_thái",
        "cảnh_quan",
        "kiến_thức",
    }
)
LIGHT_TAGS = frozenset(
    {
        "culture",
        "history",
        "nature",
        "local_experience",
        "văn_hóa",
        "lịch_sử",
        "thiên_nhiên",
        "địa_phương",
        "ẩm_thực",
        "đồ_uống",
        "phong_cách_việt",
        "phong_cách_thái",
        "phong_cách_nhật",
        "phong_cách_hàn",
        "phong_cách_trung_hoa",
        "phong_cách_phương_tây",
        "giá_rẻ",
    }
)
