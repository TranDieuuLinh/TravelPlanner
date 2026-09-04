import asyncio
import json

from app.modules.plan_editor.adapters.gemini import GeminiPlanEditIntentResolver
from app.modules.plan_editor.contract import NaturalLanguagePlanEdit, PlanEditContext
from app.modules.plan_editor.service import NaturalLanguagePlanEditor


class FakeLlmClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.call = None

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.call = (user_prompt, kwargs)
        return json.dumps(self.response, ensure_ascii=False)


class FakeResolver:
    def __init__(self, edit: NaturalLanguagePlanEdit) -> None:
        self.edit = edit
        self.payload = None

    async def resolve(self, payload: PlanEditContext) -> NaturalLanguagePlanEdit:
        self.payload = payload
        return self.edit


def _plan() -> dict:
    return {
        "destination": "Hà Nội",
        "days": [
            {
                "day": 1,
                "stops": [
                    {
                        "itemId": "item-lake",
                        "name": "Hồ Gươm",
                        "address": "Hoàn Kiếm",
                        "durationMinutes": 60,
                        "personalNotes": None,
                        "coordinates": {"latitude": 21.0, "longitude": 105.8},
                        "sourceRefs": ["private-source"],
                    }
                ],
            }
        ],
    }


def test_gemini_resolver_uses_structured_output() -> None:
    client = FakeLlmClient(
        {
            "action": "delete",
            "confidence": 0.98,
            "day": 1,
            "itemId": "item-lake",
            "itemIds": [],
            "position": None,
            "item": None,
            "response": "Đã xóa Hồ Gươm khỏi ngày 1.",
            "clarificationQuestion": None,
        }
    )
    resolver = GeminiPlanEditIntentResolver(client)

    result = asyncio.run(
        resolver.resolve(PlanEditContext(message="Xóa Hồ Gươm", plan=_plan()))
    )

    assert result.action == "delete"
    assert result.item_id == "item-lake"
    prompt, options = client.call
    assert json.loads(prompt)["message"] == "Xóa Hồ Gươm"
    assert options["temperature"] == 0.0
    assert options["response_json_schema"]["properties"]["itemId"]
    assert "default" not in json.dumps(options["response_json_schema"])


def test_editor_sends_only_compact_editable_plan_context() -> None:
    resolver = FakeResolver(NaturalLanguagePlanEdit(action="none", confidence=0.99))
    editor = NaturalLanguagePlanEditor(resolver)

    result = asyncio.run(editor.interpret("Hôm nay thời tiết sao?", _plan()))

    assert result.action == "none"
    item = resolver.payload.plan["days"][0]["items"][0]
    assert item["itemId"] == "item-lake"
    assert "coordinates" not in item
    assert "sourceRefs" not in item


def test_editor_rejects_item_id_not_present_in_selected_day() -> None:
    resolver = FakeResolver(
        NaturalLanguagePlanEdit(
            action="delete",
            confidence=0.99,
            day=1,
            item_id="invented-item",
            response="Đã xóa.",
        )
    )
    editor = NaturalLanguagePlanEditor(resolver)

    result = asyncio.run(editor.interpret("Xóa chỗ đó", _plan()))

    assert result.action == "clarify"
    assert result.clarification_question
