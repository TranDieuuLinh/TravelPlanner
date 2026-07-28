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

    # MoMo Sandbox Settings
    momo_partner_code: str = "MOMO"
    momo_access_key: str = "F8B39C29B7F5"
    momo_secret_key: str = "K95549280BDF0E35417241123A0CE8A"
    momo_api_url: str = "https://test-payment.momo.vn/v2/gateway/api/create"
    momo_redirect_url: str = "http://localhost:3000/orders/{orderId}/result"
    momo_ipn_url: str = "http://localhost:8000/api/payments/webhooks/momo"

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
