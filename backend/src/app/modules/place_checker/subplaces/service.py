from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict

from app.modules.place_checker.subplaces.contract import (
    SubplaceGroup,
    SubplaceOfferItemContext,
    SubplaceNoteRequest,
)
from app.modules.place_checker.subplaces.ports import (
    SubplaceCatalog,
    SubplaceNoteGenerator,
)

logger = logging.getLogger(__name__)


class SubplaceDisplayService:
    """Build frontend-only SubPlace cards and Gemini-authored activity notes."""

    def __init__(
        self,
        catalog: SubplaceCatalog,
        note_generator: SubplaceNoteGenerator | None,
        *,
        batch_size: int = 12,
        cache_size: int = 2048,
    ) -> None:
        self._catalog = catalog
        self._note_generator = note_generator
        self._batch_size = max(1, batch_size)
        self._cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, str] = OrderedDict()

    async def list_subplaces(
        self,
        parent_place_ids: list[str],
        *,
        per_parent_limit: int = 50,
    ) -> list[SubplaceGroup]:
        groups = await self._catalog.list_subplaces(
            parent_place_ids,
            per_parent_limit=per_parent_limit,
        )
        requests: list[SubplaceNoteRequest] = []
        pending_ids: set[str] = set()
        item_keys: dict[tuple[int, int], str] = {}
        for group_index, group in enumerate(groups):
            parent_name = group.parent_place_name or group.parent_place_id
            for item_index, item in enumerate(group.items):
                if not item.offer_items:
                    continue
                request_id = self._cache_key(parent_name, item.name, item.offer_items)
                item_keys[(group_index, item_index)] = request_id
                if request_id not in self._cache and request_id not in pending_ids:
                    pending_ids.add(request_id)
                    requests.append(
                        SubplaceNoteRequest(
                            request_id=request_id,
                            parent_place_name=parent_name,
                            subplace_name=item.name,
                            offer_items=item.offer_items,
                        )
                    )

        generated = await self._generate(requests)
        result: list[SubplaceGroup] = []
        for group_index, group in enumerate(groups):
            items = []
            for item_index, item in enumerate(group.items):
                request_id = item_keys.get((group_index, item_index))
                note = self._cache.get(request_id or "") or generated.get(request_id or "")
                if note:
                    items.append(
                        item.model_copy(
                            update={
                                "note": note,
                                "note_source": "gemini",
                                "note_activity_item_ids": [
                                    offer.activity_item_id for offer in item.offer_items
                                ],
                            }
                        )
                    )
                else:
                    items.append(
                        item.model_copy(
                            update={
                                "note": None,
                                "note_source": None,
                                "note_activity_item_ids": [],
                            }
                        )
                    )
            result.append(group.model_copy(update={"items": items}))
        return result

    async def _generate(
        self,
        requests: list[SubplaceNoteRequest],
    ) -> dict[str, str]:
        generated: dict[str, str] = {}
        if self._note_generator is None:
            return generated
        for offset in range(0, len(requests), self._batch_size):
            batch = requests[offset : offset + self._batch_size]
            try:
                batch_result = await self._note_generator.generate_many(batch)
            except Exception as exc:
                logger.warning(
                    "SubPlace Gemini note generation failed (%s)",
                    type(exc).__name__,
                )
                continue
            expected_ids = {request.request_id for request in batch}
            for request_id, note in batch_result.items():
                normalized = note.strip() if isinstance(note, str) else ""
                if request_id not in expected_ids or not normalized or len(normalized) > 300:
                    continue
                generated[request_id] = normalized
                self._remember(request_id, normalized)
        return generated

    def _remember(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _cache_key(
        parent_name: str,
        subplace_name: str,
        offer_items: list[SubplaceOfferItemContext],
    ) -> str:
        activity_payload = "\0".join(
            f"{offer.activity_item_id}\0{offer.activity_item_name}\0"
            f"{offer.action or ''}\0{offer.display_template or ''}"
            for offer in offer_items
        )
        payload = (
            f"subplace-note.vi.v1\0{parent_name}\0{subplace_name}\0{activity_payload}"
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
