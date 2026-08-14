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
    backend_cors_origins: str = "http://localhost:3000,http://localhost:3001"
    database_url: str | None = None
    conversation_memory_enabled: bool = True
    auth_dev_seed_users: str = (
        "creator@example.com|Creator Demo|Password123!|creator,"
        "admin@travelplanner.local|TravelPlanner Admin|Password123!|admin"
    )
    langfuse_host: str = "http://localhost:3005"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_timeout_seconds: float = 10.0
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
    supervisor_classifier_provider: Literal["gemini"] = "gemini"
    supervisor_llm_max_output_tokens: int = 256
    supervisor_llm_fallback_enabled: bool = True
    supervisor_llm_confidence_threshold: float = 0.65
    explorer_draft_provider: Literal["rules", "gemini"] = "rules"
    explorer_source_draft_provider: Literal["rules", "gemini"] = "gemini"
    explorer_llm_max_output_tokens: int = Field(default=4000, ge=256)
    explorer_source_chunk_characters: int = Field(default=20_000, ge=2_000, le=60_000)
    explorer_source_max_output_tokens: int = Field(default=8_000, ge=1_000)
    explorer_source_max_concurrency: int = Field(default=5, ge=1, le=20)
    explorer_synthesis_max_concurrency: int = Field(default=6, ge=1, le=20)
    explorer_minimum_synthesis_coverage: float = Field(default=0.8, gt=0, le=1)
    explorer_dedupe_provider: Literal["rules", "gemini"] = "gemini"
    explorer_note_provider: Literal["rules", "gemini"] = "gemini"
    explorer_url_timeout_seconds: float = Field(default=30.0, gt=0)
    explorer_url_cache_ttl_seconds: float = Field(default=604_800, gt=0)
    explorer_draft_cache_ttl_seconds: float = Field(default=604_800, gt=0)
    explorer_ytdlp_cookie_file: str | None = None
    explorer_frame_interval_seconds: float = Field(default=3.0, gt=0)
    explorer_frame_batch_size: int = Field(default=10, ge=1, le=10)
    explorer_max_frames: int = Field(default=48, ge=1, le=72)
    explorer_frame_max_concurrency: int = Field(default=5, ge=1, le=8)
    explorer_audio_chunk_count: int = Field(default=3, ge=1, le=8)
    explorer_audio_chunk_seconds: float = Field(default=60.0, gt=0)
    explorer_youtube_audio_chunk_seconds: int = Field(default=300, ge=30, le=900)
    explorer_youtube_audio_chunk_overlap_seconds: int = Field(default=5, ge=0, le=30)
    explorer_youtube_audio_max_concurrency: int = Field(default=8, ge=1, le=20)
    explorer_youtube_max_duration_seconds: int = Field(default=14_400, ge=60)
    explorer_max_video_seconds: float = Field(default=180.0, gt=0)
    explorer_max_media_mb: int = Field(default=120, ge=1)
    information_finder_embedding_model: str = "gemini-embedding-001"
    information_finder_embedding_revision: str | None = None
    information_finder_embedding_output_dimensions: int = 384
    information_finder_embedding_timeout_seconds: float = 30.0
    information_finder_chunking_provider: Literal["deterministic", "gemini_url"] = (
        "gemini_url"
    )
    information_finder_chunking_max_output_tokens: int = 8000
    information_finder_min_local_sources: int = 2
    information_finder_similarity_threshold: float = 0.8
    information_finder_relevance_threshold: float = 0.5
    information_finder_blocked_domains: str = ""
    information_finder_answer_provider: Literal["extractive", "gemini"] = "extractive"
    information_finder_llm_max_output_tokens: int = 800
    information_finder_llm_max_chars_per_source: int = 4000
    information_finder_llm_max_total_source_chars: int = 12000
    information_finder_llm_fallback_enabled: bool = True
    google_maps_scraper_enabled: bool = True
    google_maps_scraper_timeout_seconds: float = Field(default=90.0, gt=0)
    google_maps_scraper_max_alias_queries: int = Field(default=2, ge=0, le=5)
    google_maps_scraper_max_concurrency: int = Field(default=3, ge=1, le=5)
    route_provider: Literal["valhalla", "disabled"] = "valhalla"
    valhalla_base_url: str = "http://localhost:8002"
    valhalla_timeout_seconds: float = Field(default=15.0, gt=0)
    valhalla_graph_version: str = "local"
    itinerary_log_search_progress: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
