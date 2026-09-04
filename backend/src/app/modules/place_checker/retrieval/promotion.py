from app.modules.place_checker.enums import PromotionEventStatus
from app.modules.place_checker.ports import PromotionCatalog, PromotionOutbox
from app.modules.place_checker.retrieval.contract import PromotionWorkResult


class PromotionWorker:
    def __init__(
        self,
        outbox: PromotionOutbox,
        catalog: PromotionCatalog,
    ) -> None:
        self.outbox = outbox
        self.catalog = catalog

    async def run_once(self, limit: int = 20) -> list[PromotionWorkResult]:
        events = await self.outbox.claim(limit)
        results: list[PromotionWorkResult] = []
        for event in events:
            try:
                duplicate_id = await self.catalog.find_duplicate(event.candidate)
                entity_id = duplicate_id or await self.catalog.promote(event.candidate)
                await self.outbox.mark_promoted(event.event_id, entity_id)
                results.append(
                    PromotionWorkResult(
                        event_id=event.event_id,
                        status=PromotionEventStatus.promoted,
                        entity_id=entity_id,
                        duplicate=duplicate_id is not None,
                    )
                )
            except Exception:
                error_code = "promotion_worker_error"
                await self.outbox.mark_failed(event.event_id, error_code)
                results.append(
                    PromotionWorkResult(
                        event_id=event.event_id,
                        status=PromotionEventStatus.failed,
                        error_code=error_code,
                    )
                )
        return results
