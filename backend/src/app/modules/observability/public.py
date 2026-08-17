from app.core.config import Settings
from app.modules.observability.local_store import LocalObservabilityStore
from app.modules.observability.router import router
from app.modules.observability.service import ObservabilityService


from app.shared.observability import create_observability_manager


def build_observability_service(settings: Settings) -> ObservabilityService:
    store = LocalObservabilityStore()
    manager = create_observability_manager(settings, local_store=store)
    return ObservabilityService(store=store, manager=manager)


__all__ = ["build_observability_service", "router"]
