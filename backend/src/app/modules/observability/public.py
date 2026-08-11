from app.core.config import Settings
from app.modules.observability.adapters.langfuse_http import LangfuseHttpClient
from app.modules.observability.router import router
from app.modules.observability.service import ObservabilityService


def build_observability_service(settings: Settings) -> ObservabilityService:
    return ObservabilityService(
        LangfuseHttpClient(
            settings.langfuse_host,
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
            settings.langfuse_timeout_seconds,
        ),
        settings.langfuse_host,
    )


__all__ = ["build_observability_service", "router"]
