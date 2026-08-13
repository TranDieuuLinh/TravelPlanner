from app.core.config import Settings
from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.router import router
from app.modules.observability.service import ObservabilityService


def build_observability_service(settings: Settings) -> ObservabilityService:
    return ObservabilityService(LocalObservabilityStore())


__all__ = ["build_observability_service", "router"]
