import json
from typing import Any

from app.modules.plan_editor.contract import NaturalLanguagePlanEdit, PlanEditContext
from app.modules.plan_editor.prompts import PLAN_EDIT_INTERPRETER_SYSTEM_PROMPT
from app.shared.llm import LlmClient


class GeminiPlanEditIntentResolver:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 700) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def resolve(self, payload: PlanEditContext) -> NaturalLanguagePlanEdit:
        response = await self._client.generate(
            json.dumps(
                payload.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            system_prompt=PLAN_EDIT_INTERPRETER_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=self._schema(),
        )
        return NaturalLanguagePlanEdit.model_validate_json(response)

    @staticmethod
    def _schema() -> dict[str, Any]:
        return _provider_schema(
            NaturalLanguagePlanEdit.model_json_schema(by_alias=True)
        )


def _provider_schema(value: Any) -> Any:
    """Remove Pydantic defaults unsupported by Gemini response schemas."""
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value
