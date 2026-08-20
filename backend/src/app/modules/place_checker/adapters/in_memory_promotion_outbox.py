from app.modules.place_checker.enums import PromotionEventStatus
from app.modules.place_checker.retrieval.contract import PromotionEvent


class InMemoryPromotionOutbox:
    """Development/test outbox; production wiring needs durable persistence."""

    def __init__(self) -> None:
        self.events: dict[str, PromotionEvent] = {}

    async def enqueue(self, event: PromotionEvent) -> bool:
        if event.event_id in self.events:
            return False
        self.events[event.event_id] = event
        return True

    async def claim(self, limit: int) -> list[PromotionEvent]:
        pending = [
            event
            for event in self.events.values()
            if event.status == PromotionEventStatus.pending
        ][:limit]
        for event in pending:
            self.events[event.event_id] = event.model_copy(
                update={"status": PromotionEventStatus.processing}
            )
        return [self.events[event.event_id] for event in pending]

    async def mark_promoted(self, event_id: str, entity_id: str) -> None:
        event = self.events[event_id]
        self.events[event_id] = event.model_copy(
            update={
                "status": PromotionEventStatus.promoted,
                "promoted_entity_id": entity_id,
                "error_code": None,
            }
        )

    async def mark_failed(self, event_id: str, error_code: str) -> None:
        event = self.events[event_id]
        self.events[event_id] = event.model_copy(
            update={
                "status": PromotionEventStatus.failed,
                "error_code": error_code,
            }
        )
