import json
from typing import Any

from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.prompts import build_classifier_prompt
from app.shared.llm import LlmClient


class GeminiIntentClassifier:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 256) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        user_payload = {
            "message": payload.message,
            "conversationContext": [
                item[-500:] for item in payload.conversation_context
            ],
            "hasItinerary": payload.has_itinerary,
            "hasEditOperation": payload.has_edit_operation,
        }
        response = await self._client.generate(
            json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            system_prompt=build_classifier_prompt(),
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=self._schema(),
        )
        return ClassifierResult.model_validate_json(response)

    @staticmethod
    def _schema() -> dict[str, Any]:
        return ClassifierResult.model_json_schema()
