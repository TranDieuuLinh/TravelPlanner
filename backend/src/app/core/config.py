from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str | None = None
    tavily_api_key: str | None = None
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = 5
    tavily_timeout_seconds: float = 15.0
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 30.0
    gemini_key_cooldown_seconds: float = 60.0
    information_finder_embedding_model: str = "intfloat/multilingual-e5-small"
    information_finder_embedding_revision: str | None = None
    information_finder_min_local_sources: int = 2
    information_finder_similarity_threshold: float = 0.65
    information_finder_relevance_threshold: float = 0.5
    information_finder_blocked_domains: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

