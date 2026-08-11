from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
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
    gemini_audio_model: str = "gemini-2.5-flash"
    gemini_image_ocr_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 30.0
    gemini_key_cooldown_seconds: float = 60.0
    supervisor_classifier_provider: Literal["rules", "gemini"] = "rules"
    supervisor_llm_max_output_tokens: int = 256
    supervisor_llm_fallback_enabled: bool = True
    supervisor_llm_confidence_threshold: float = 0.65
    explorer_draft_provider: Literal["rules", "gemini"] = "rules"
    explorer_llm_max_output_tokens: int = Field(default=4000, ge=256)
    explorer_url_timeout_seconds: float = Field(default=30.0, gt=0)
    explorer_url_cache_ttl_seconds: float = Field(default=604_800, gt=0)
    explorer_draft_cache_ttl_seconds: float = Field(default=604_800, gt=0)
    explorer_ytdlp_cookie_file: str | None = None
    explorer_frame_interval_seconds: float = Field(default=1.5, gt=0)
    explorer_frame_batch_size: int = Field(default=10, ge=1, le=10)
    explorer_max_frames: int = Field(default=72, ge=1, le=72)
    explorer_frame_max_concurrency: int = Field(default=5, ge=1, le=8)
    explorer_audio_chunk_count: int = Field(default=3, ge=1, le=8)
    explorer_max_video_seconds: float = Field(default=180.0, gt=0)
    explorer_max_media_mb: int = Field(default=120, ge=1)
    information_finder_embedding_model: str = "gemini-embedding-001"
    information_finder_embedding_revision: str | None = None
    information_finder_embedding_output_dimensions: int = 384
    information_finder_embedding_timeout_seconds: float = 30.0
    information_finder_min_local_sources: int = 2
    information_finder_similarity_threshold: float = 0.65
    information_finder_relevance_threshold: float = 0.5
    information_finder_blocked_domains: str = ""
    information_finder_answer_provider: Literal["extractive", "gemini"] = "extractive"
    information_finder_llm_max_output_tokens: int = 800
    information_finder_llm_max_chars_per_source: int = 4000
    information_finder_llm_max_total_source_chars: int = 12000
    information_finder_llm_fallback_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
