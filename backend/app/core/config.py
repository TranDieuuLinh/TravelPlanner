from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "VSF Travel API"
    app_env: str = "local"
    database_url: str = "sqlite:///./vsf_travel.db"
    backend_cors_origins: str = Field(default="http://localhost:3000")
    preload_url_reel_models: bool = False
    enable_llm_explore_formatter: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_audio_model: str = "gemini-3.6-flash"
    gemini_image_ocr_model: str = "gemini-3.5-flash-lite"
    place_resolver_provider: str = "nominatim"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "VSF-Travel-Planner/0.1 (local-development)"
    nominatim_timeout_seconds: float = 15.0
    nominatim_min_interval_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
