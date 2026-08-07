from __future__ import annotations

import json

from app.modules.plans.place_selector.meal_node_planner import MealNodePlanner


class _Node:
    def __init__(self, node_id: str, name: str, node_type: str) -> None:
        self.id = node_id
        self.canonical_name = name
        self.entity_type = node_type


class _Graph:
    def list_meal_item_nodes(self, *, limit: int):
        assert limit == 100
        return [
            _Node("food-pho", "Phở", "FoodItem"),
            _Node("food-com", "Cơm", "FoodItem"),
            _Node("drink-coffee", "Cà phê", "DrinkItem"),
        ]


class _LLM:
    async def generate_structured_json(self, system_prompt, user_payload, *, response_schema):
        assert "FoodItem" in system_prompt
        assert "DrinkItem" in system_prompt
        payload = json.loads(user_payload)
        assert payload["activities"][0]["name"] == "Văn Miếu"
        return json.dumps(
            {
                "selections": [
                    {
                        "slot": "breakfast",
                        "nodeId": "food-pho",
                        "nodeName": "Phở",
                        "nodeType": "FoodItem",
                    },
                    {
                        "slot": "lunch",
                        "nodeId": "food-com",
                        "nodeName": "Cơm",
                        "nodeType": "FoodItem",
                    },
                ]
            }
        )


def test_meal_node_planner_uses_vietnamese_llm_contract_and_catalog_ids() -> None:
    result = MealNodePlanner(_LLM(), _Graph()).select_for_day(
        activities=[{"name": "Văn Miếu", "timeWindow": "09:00-11:00"}],
        interests=["culture", "food"],
        used_node_names=set(),
    )

    assert [(item.slot, item.node_id, item.node_name) for item in result] == [
        ("breakfast", "food-pho", "Phở"),
        ("lunch", "food-com", "Cơm"),
    ]


class _HallucinatingLLM(_LLM):
    async def generate_structured_json(self, system_prompt, user_payload, *, response_schema):
        return json.dumps(
            {
                "selections": [
                    {
                        "slot": "breakfast",
                        "nodeId": "not-in-catalog",
                        "nodeName": "Bún chả",
                        "nodeType": "FoodItem",
                    }
                ]
            }
        )


def test_meal_node_planner_discards_unknown_graph_nodes() -> None:
    result = MealNodePlanner(_HallucinatingLLM(), _Graph()).select_for_day(
        activities=[{"name": "Văn Miếu"}],
        interests=[],
        used_node_names=set(),
    )

    assert result == []
