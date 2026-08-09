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


class TripMealNodeSelection(MealNodeSelection):
    day: int = Field(ge=1, le=30)


class TripMealNodeSelectionResponse(BaseModel):
    selections: list[TripMealNodeSelection] = Field(default_factory=list)

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


TRIP_MEAL_NODE_SYSTEM_PROMPT = """
Bạn là bộ chọn món cho toàn bộ chuyến đi trong hệ thống lập lịch du lịch.

Nhiệm vụ: đọc các hoạt động đã được PlaceSelector xếp theo từng ngày và chọn
FoodItem hoặc DrinkItem cho breakfast, lunch, dinner của từng ngày.

Quy tắc bắt buộc:
- Chỉ chọn node có trong mealNodeCatalog; giữ nguyên chính xác nodeId, nodeName,
  nodeType và chỉ trả JSON đúng schema.
- Mỗi cặp day + slot xuất hiện tối đa một lần.
- Ưu tiên món phù hợp thời điểm, hoạt động, địa phương và sở thích chuyến đi.
- Trong cùng một ngày, không chọn ba món quá giống nhau nếu catalog còn lựa chọn.
- Không lặp lại cùng node trong toàn chuyến nếu vẫn còn node phù hợp khác.
- DrinkItem chỉ nên đi cùng bữa khi đó là lựa chọn hợp lý; không biến quán cà phê,
  bar hoặc tiệm tráng miệng thành bữa chính.
- Không chọn tên nhà hàng. Backend sẽ tìm Restaurant có cạnh OFFERS_ITEM tới node.
- Có thể bỏ trống slot nếu catalog không có node phù hợp có thể phục vụ như bữa chính.
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

    def select_for_trip(
        self,
        *,
        activities_by_day: dict[int, list[dict[str, Any]]],
        interests: list[str],
        unavailable_node_ids: set[str] | None = None,
    ) -> list[TripMealNodeSelection]:
        """Make one bounded LLM call for the entire trip, never one per slot/day."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                self._select_for_trip(
                    activities_by_day=activities_by_day,
                    interests=interests,
                    unavailable_node_ids=unavailable_node_ids or set(),
                ),
            )
            return future.result()

    def _catalog(self) -> list[dict[str, str]]:
        loader = getattr(
            self.graph_repository,
            "list_plannable_meal_item_nodes",
            None,
        )
        if not callable(loader):
            loader = self.graph_repository.list_meal_item_nodes
        nodes = loader(limit=100)
        return [
            {
                "nodeId": node.id,
                "nodeName": node.canonical_name,
                "nodeType": node.entity_type,
            }
            for node in nodes
        ]

    async def _select_for_day(
        self,
        *,
        activities: list[dict[str, Any]],
        interests: list[str],
        used_node_names: set[str],
        unavailable_node_ids: set[str],
    ) -> list[MealNodeSelection]:
        catalog = self._catalog()
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

    async def _select_for_trip(
        self,
        *,
        activities_by_day: dict[int, list[dict[str, Any]]],
        interests: list[str],
        unavailable_node_ids: set[str],
    ) -> list[TripMealNodeSelection]:
        catalog = self._catalog()
        if not catalog or not activities_by_day:
            return []
        payload = json.dumps(
            {
                "days": [
                    {"day": day, "activities": activities}
                    for day, activities in sorted(activities_by_day.items())
                ],
                "interests": interests,
                "unavailableNodeIds": sorted(unavailable_node_ids),
                "mealNodeCatalog": catalog,
            },
            ensure_ascii=False,
        )
        raw = await self.llm.generate_structured_json(
            TRIP_MEAL_NODE_SYSTEM_PROMPT,
            payload,
            response_schema=TripMealNodeSelectionResponse.model_json_schema(),
        )
        response = TripMealNodeSelectionResponse.model_validate_json(raw)
        valid = {node["nodeId"]: node for node in catalog}
        valid_days = set(activities_by_day)
        result: list[TripMealNodeSelection] = []
        seen_slots: set[tuple[int, str]] = set()
        used_nodes: set[str] = set()
        for selection in response.selections:
            catalog_node = valid.get(selection.node_id)
            slot_key = (selection.day, selection.slot)
            if catalog_node is None or selection.day not in valid_days:
                continue
            if slot_key in seen_slots or selection.node_id in used_nodes:
                continue
            if selection.node_id in unavailable_node_ids:
                continue
            if selection.node_name.casefold() != catalog_node["nodeName"].casefold():
                continue
            if selection.node_type != catalog_node["nodeType"]:
                continue
            result.append(
                selection.model_copy(
                    update={"node_name": catalog_node["nodeName"]}
                )
            )
            seen_slots.add(slot_key)
            used_nodes.add(selection.node_id)
        return result
