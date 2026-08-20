import json
from typing import Any

from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.prompts import build_classifier_prompt
from app.shared.llm import LlmClient


class GeminiIntentClassifier:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 1024) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        user_payload = {
            "message": payload.message,
            "conversationContext": [
                item[-500:] for item in payload.conversation_context[-6:]
            ],
            "hasItinerary": payload.has_itinerary,
            "hasEditOperation": payload.has_edit_operation,
            "destination": payload.destination,
            "durationDays": payload.duration_days,
            "mentionedPlaces": payload.mentioned_places[-50:],
            "selectedPlaces": payload.selected_places[-50:],
            "clarificationRequired": payload.clarification_required,
            "conversationSummary": (payload.conversation_summary or "")[-2000:],
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
        schema = ClassifierResult.model_json_schema()
        schema["properties"]["suggestions"]["items"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "field": {"type": "string", "enum": ["follow_up"]},
                "label": {"type": "string", "minLength": 1, "maxLength": 60},
                "value": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "required": ["field", "label", "value"],
        }
        return schema
