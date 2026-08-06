from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _gemini_keys(value: str | None) -> tuple[str, ...]:
    return tuple(
        key.strip()
        for key in (value or "").split(",")
        if key.strip()
    )


class Settings(BaseSettings):
    app_name: str = "VSF Travel API"
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
    backend_cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001"
    )
    jwt_secret: str = "local-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 1440
    refresh_token_days: int = 7
    auth_cookie_secure: bool = False

    # MoMo Sandbox Settings
    momo_partner_code: str = "MOMO"
    momo_access_key: str = "F8B39C29B7F5"
    momo_secret_key: str = "K95549280BDF0E35417241123A0CE8A"
    momo_api_url: str = "https://test-payment.momo.vn/v2/gateway/api/create"
    momo_redirect_url: str = "http://localhost:3000/orders/{orderId}/result"
    momo_ipn_url: str = "http://localhost:8000/api/payments/webhooks/momo"
    preload_url_reel_models: bool = False
    enable_llm_explore_formatter: bool = False
    conversation_supervisor_enabled: bool = True
    conversation_supervisor_llm_enabled: bool = True
    auto_plan_mutation_enabled: bool = True
    conversation_streaming_enabled: bool = True
    conversation_turn_timeout_seconds: float = Field(default=120.0, ge=1.0, le=900.0)
    conversation_plan_timeout_seconds: float = Field(default=300.0, ge=30.0, le=1800.0)
    conversation_turn_stale_after_seconds: float = Field(default=360.0, ge=1.0, le=3600.0)
    candidate_review_enabled: bool = False
    weather_enabled: bool = False
    conversational_backup_enabled: bool = True
    partner_search_enabled: bool = False
    realtime_collaboration_enabled: bool = False
    weatherapi_key: str | None = None
    weatherapi_base_url: str = "https://api.weatherapi.com/v1"
    gemini_api_key: str | None = None
    gemini_stt_api_keys: str | None = None
    gemini_ocr_api_keys: str | None = None
    gemini_caption_api_keys: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_min_interval_seconds: float = Field(default=0.0, ge=0.0)
    gemini_caption_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=120.0,
    )
    gemini_caption_max_attempts: int = Field(default=2, ge=1, le=3)
    gemini_audio_model: str = "gemini-3.6-flash"
    gemini_image_ocr_model: str = "gemini-3.5-flash-lite"
    url_reel_gemini_stt_min_interval_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
    )
    url_reel_stt_chunk_seconds: float = Field(default=60.0, ge=45.0, le=300.0)
    url_reel_stt_max_concurrency: int = Field(default=3, ge=1, le=4)
    url_reel_stt_overlap_seconds: float = Field(default=2.0, ge=0.0, le=5.0)
    url_reel_max_frames: int = 72
    url_reel_min_frame_interval_seconds: float = 1.0
    url_reel_frame_width: int = 960
    url_reel_vision_batch_size: int = 10
    url_reel_vision_max_concurrency: int = 5
    url_reel_vision_media_resolution: str = "MEDIA_RESOLUTION_MEDIUM"
    url_reel_network_timeout_seconds: float = Field(
        default=30.0,
        ge=5.0,
        le=120.0,
    )
    url_reel_subprocess_timeout_seconds: float = Field(
        default=180.0,
        ge=10.0,
        le=600.0,
    )
    web_page_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    web_page_max_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=64 * 1024,
        le=20 * 1024 * 1024,
    )
    web_page_max_redirects: int = Field(default=5, ge=0, le=10)
    web_page_max_text_chars: int = Field(default=60_000, ge=1_000, le=500_000)
    url_import_job_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        le=3600.0,
    )
    youtube_transcript_min_interval_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=60.0,
    )
    youtube_transcript_worker_url: str | None = None
    youtube_transcript_worker_token: str | None = None
    youtube_transcript_worker_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
    )
    explorer_timing_log_path: Path = (
        BACKEND_ROOT / "var" / "explorer-timings.jsonl"
    )
    user_post_media_dir: Path = BACKEND_ROOT / "var" / "user-post-media"
    user_post_image_max_bytes: int = 15 * 1024 * 1024
    user_post_video_max_bytes: int = 100 * 1024 * 1024
    place_resolver_provider: str = "google_maps_scraper"
    route_provider: str = "valhalla"
    itinerary_optimizer_mode: str = "route_first"
    valhalla_base_url: str = "http://localhost:8002"
    valhalla_timeout_seconds: float = 15.0
    valhalla_min_interval_seconds: float = Field(default=0.0, ge=0.0)
    opentripplanner_base_url: str = (
        "http://localhost:8080/otp/gtfs/v1"
    )
    opentripplanner_timeout_seconds: float = 35.0
    opentripplanner_schedule_status: str = "current"
    google_maps_scraper_executable: str | None = "google-maps-scraper"
    google_maps_scraper_work_dir: Path | None = None
    google_maps_scraper_timeout_seconds: float = Field(
        default=90.0,
        ge=1.0,
        le=300.0,
    )
    google_maps_scraper_max_alias_queries: int = Field(
        default=2,
        ge=1,
        le=10,
    )
    google_maps_scraper_max_concurrency: int = Field(
        default=2,
        ge=1,
        le=4,
    )
    database_place_resolver_top_k: int = Field(default=5, ge=1, le=50)
    database_place_resolver_minimum_score: float = Field(
        default=0.82,
        ge=0.0,
        le=1.0,
    )
    database_place_resolver_minimum_margin: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def gemini_stt_key_pool(self) -> tuple[str, ...]:
        dedicated = _gemini_keys(self.gemini_stt_api_keys)
        if dedicated:
            return dedicated
        shared = _gemini_keys(self.gemini_api_key)
        dedicated_ocr = set(_gemini_keys(self.gemini_ocr_api_keys))
        available = tuple(key for key in shared if key not in dedicated_ocr)
        if self.gemini_ocr_api_keys:
            return available
        split_index = max(1, len(shared) // 2)
        return shared[:split_index]

    @property
    def gemini_ocr_key_pool(self) -> tuple[str, ...]:
        dedicated = _gemini_keys(self.gemini_ocr_api_keys)
        if dedicated:
            return dedicated
        shared = _gemini_keys(self.gemini_api_key)
        dedicated_stt = set(_gemini_keys(self.gemini_stt_api_keys))
        available = tuple(key for key in shared if key not in dedicated_stt)
        if self.gemini_stt_api_keys:
            return available
        split_index = max(1, len(shared) // 2)
        return shared[split_index:] or shared[:1]

    @property
    def gemini_caption_key_pool(self) -> tuple[str, ...]:
        """Use dedicated caption keys or borrow every idle STT/OCR key.

        Long-form YouTube caption structuring does not run audio STT or frame
        OCR, so the text-only step may safely load-balance over both pools.
        """
        dedicated = _gemini_keys(self.gemini_caption_api_keys)
        if dedicated:
            return tuple(dict.fromkeys(dedicated))
        return tuple(
            dict.fromkeys(
                (*self.gemini_stt_key_pool, *self.gemini_ocr_key_pool)
            )
        )

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
        stt_keys = set(_gemini_keys(self.gemini_stt_api_keys))
        ocr_keys = set(_gemini_keys(self.gemini_ocr_api_keys))
        if stt_keys & ocr_keys:
            raise ValueError(
                "GEMINI_STT_API_KEYS and GEMINI_OCR_API_KEYS must use "
                "different keys."
            )
        if self.place_resolver_provider not in {
            "google_maps_scraper",
            "provisional",
        }:
            raise ValueError(
                "PLACE_RESOLVER_PROVIDER must be google_maps_scraper or "
                "provisional"
            )
        if self.route_provider not in {"valhalla", "geodesic"}:
            raise ValueError(
                "ROUTE_PROVIDER must be valhalla or geodesic"
            )
        if self.itinerary_optimizer_mode not in {"route_first", "legacy"}:
            raise ValueError(
                "ITINERARY_OPTIMIZER_MODE must be route_first or legacy"
            )
        if bool(self.youtube_transcript_worker_url) != bool(
            self.youtube_transcript_worker_token
        ):
            raise ValueError(
                "YOUTUBE_TRANSCRIPT_WORKER_URL and "
                "YOUTUBE_TRANSCRIPT_WORKER_TOKEN must be configured together"
            )
        if not self.database_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL; SQLite is supported only "
                "by isolated test engines"
            )
        if self.app_env not in {"local", "test"}:
            if self.jwt_secret == "local-only-change-me":
                raise ValueError("JWT_SECRET must be configured outside local/test environments")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true outside local/test environments")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
