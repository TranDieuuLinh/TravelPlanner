"""LLM selection of graph food/drink nodes after daily activities are known."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.llm.base import LLMClient


class MealNodeSelection(BaseModel):
    slot: str = Field(pattern=r"^(breakfast|lunch|dinner)$")
    node_id: str = Field(alias="nodeId", min_length=1)
    node_name: str = Field(alias="nodeName", min_length=1)
    node_type: str = Field(alias="nodeType", pattern=r"^(FoodItem|DrinkItem)$")
    rationale: str = ""

    model_config = {"populate_by_name": True, "extra": "forbid"}


class MealNodeSelectionResponse(BaseModel):
    selections: list[MealNodeSelection] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


MEAL_NODE_SYSTEM_PROMPT = """
Bạn là bộ chọn món ăn cho hệ thống lập lịch du lịch.

Nhiệm vụ: đọc các hoạt động đã được PlaceSelector xếp cho một ngày và chọn
FoodItem hoặc DrinkItem phù hợp cho các slot breakfast, lunch, dinner.

Quy tắc bắt buộc:
- Chỉ được chọn node có trong mealNodeCatalog được cung cấp.
- Chỉ trả về JSON đúng schema, không thêm văn bản ngoài JSON.
- Không lặp món đã dùng trong ngày nếu catalog còn món khác.
- Chọn món phù hợp với hoạt động, thời điểm và sở thích của chuyến đi.
- Nếu không có món cụ thể phù hợp, chọn node tổng quát như nhà hàng, món ăn,
  đồ uống hoặc cà phê nếu các node đó có trong catalog.
- Không chọn tên nhà hàng/địa điểm. Bạn chỉ chọn FoodItem hoặc DrinkItem;
  backend sẽ tìm địa điểm có edge OFFERS_ITEM.
""".strip()


class MealNodePlanner:
    def __init__(self, llm: LLMClient, graph_repository) -> None:
        self.llm = llm
        self.graph_repository = graph_repository

    def select_for_day(
        self,
        *,
        activities: list[dict[str, Any]],
        interests: list[str],
        used_node_names: set[str],
        unavailable_node_ids: set[str] | None = None,
    ) -> list[MealNodeSelection]:
        """Synchronous adapter for PlaceSelector's deterministic pipeline."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                self._select_for_day(
                    activities=activities,
                    interests=interests,
                    used_node_names=used_node_names,
                    unavailable_node_ids=unavailable_node_ids or set(),
                ),
            )
            return future.result()

    async def _select_for_day(
        self,
        *,
        activities: list[dict[str, Any]],
        interests: list[str],
        used_node_names: set[str],
        unavailable_node_ids: set[str],
    ) -> list[MealNodeSelection]:
        nodes = self.graph_repository.list_meal_item_nodes(limit=100)
        catalog = [
            {"nodeId": node.id, "nodeName": node.canonical_name, "nodeType": node.entity_type}
            for node in nodes
        ]
        if not catalog:
            return []
        payload = json.dumps(
            {
                "activities": activities,
                "interests": interests,
                "usedNodeNames": sorted(used_node_names),
                "unavailableNodeIds": sorted(unavailable_node_ids),
                "mealNodeCatalog": catalog,
            },
            ensure_ascii=False,
        )
        raw = await self.llm.generate_structured_json(
            MEAL_NODE_SYSTEM_PROMPT,
            payload,
            response_schema=MealNodeSelectionResponse.model_json_schema(),
        )
        response = MealNodeSelectionResponse.model_validate_json(raw)
        valid = {node["nodeId"]: node for node in catalog}
        result: list[MealNodeSelection] = []
        seen_slots: set[str] = set()
        for selection in response.selections:
            catalog_node = valid.get(selection.node_id)
            if catalog_node is None or selection.slot in seen_slots:
                continue
            if selection.node_id in unavailable_node_ids:
                continue
            if selection.node_name.casefold() != catalog_node["nodeName"].casefold():
                continue
            if selection.node_name.casefold() in used_node_names:
                continue
            result.append(selection.model_copy(update={"node_name": catalog_node["nodeName"]}))
            seen_slots.add(selection.slot)
        return result
