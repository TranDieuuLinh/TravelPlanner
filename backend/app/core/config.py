from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "VSF Travel API"
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
    backend_cors_origins: str = Field(default="http://localhost:3000")
    jwt_secret: str = "local-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
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
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_min_interval_seconds: float = Field(default=0.0, ge=0.0)
    gemini_audio_model: str = "gemini-3.6-flash"
    gemini_image_ocr_model: str = "gemini-3.5-flash-lite"
    url_reel_max_frames: int = 48
    url_reel_min_frame_interval_seconds: float = 1.0
    url_reel_frame_width: int = 960
    url_reel_vision_batch_size: int = 10
    url_reel_vision_max_concurrency: int = 5
    url_reel_vision_media_resolution: str = "MEDIA_RESOLUTION_MEDIUM"
    place_resolver_provider: str = "nominatim"
    here_base_url: str = "https://discover.search.hereapi.com"
    here_geocode_base_url: str = "https://geocode.search.hereapi.com"
    here_api_key: str | None = None
    here_timeout_seconds: float = 10.0
    here_country_code: str = "VNM"
    here_language: str = "vi-VN"
    here_min_interval_seconds: float = 0.2
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "VSF-Travel-Planner/0.1 (local-development)"
    nominatim_timeout_seconds: float = 15.0
    nominatim_min_interval_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
        if self.place_resolver_provider not in {
            "here",
            "nominatim",
            "provisional",
        }:
            raise ValueError(
                "PLACE_RESOLVER_PROVIDER must be here, nominatim, "
                "or provisional"
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
