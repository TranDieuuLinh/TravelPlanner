from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VSF Travel API"
    app_env: str = "local"
    database_url: str = "sqlite:///./vsf_travel.db"
    backend_cors_origins: str = Field(default="http://localhost:3000")
    jwt_secret: str = "local-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    auth_cookie_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_auth_settings(self) -> "Settings":
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
