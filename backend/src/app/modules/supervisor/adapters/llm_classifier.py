import json
import logging
from typing import Any

from pydantic import ValidationError

from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.prompts import build_classifier_prompt
from app.shared.llm import LlmClient


logger = logging.getLogger(__name__)


class GeminiIntentClassifier:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 2048) -> None:
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
            "currentPlan": payload.current_plan,
            "destination": payload.destination,
            "durationDays": payload.duration_days,
            "mentionedPlaces": payload.mentioned_places[-50:],
            "selectedPlaces": payload.selected_places[-50:],
            "clarificationRequired": payload.clarification_required,
            "conversationSummary": (payload.conversation_summary or "")[-2000:],
            "explorerOutput": payload.explorer_output,
            "pendingReviewKind": payload.pending_review_kind,
            "pendingReviewFields": payload.pending_review_fields,
        }
        schema = self._schema()
        response = await self._client.generate(
            json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            system_prompt=build_classifier_prompt(),
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=schema,
        )
        try:
            return ClassifierResult.model_validate_json(response)
        except (ValidationError, json.JSONDecodeError) as first_error:
            try:
                parsed = json.loads(response)
                output_shape = {
                    key: type(value).__name__ for key, value in parsed.items()
                } if isinstance(parsed, dict) else type(parsed).__name__
            except json.JSONDecodeError:
                output_shape = "invalid_json"
            logger.warning(
                "Supervisor structured output validation failed; attempting repair "
                "errors=%s output_shape=%s response_chars=%d",
                getattr(first_error, "errors", lambda: str(first_error))(),
                output_shape,
                len(response),
            )
            repair_prompt = json.dumps(
                {
                    "invalidOutput": response[:6000],
                    "validationError": str(first_error)[:2000],
                    "instruction": (
                        "Return only a corrected JSON object matching the supplied schema. "
                        "route must be one of explorer, information_finder, plan_editor, finish; "
                        "confidence must be a JSON number from 0 to 1, never a label such as high."
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            repaired = await self._client.generate(
                repair_prompt,
                system_prompt=(
                    "You repair invalid structured output. Return JSON only. "
                    "Do not add fields and do not explain the repair."
                ),
                temperature=0.0,
                max_output_tokens=self._max_output_tokens,
                response_json_schema=schema,
            )
            try:
                return ClassifierResult.model_validate_json(repaired)
            except (ValidationError, json.JSONDecodeError) as repair_error:
                logger.warning(
                    "Supervisor structured output repair failed; "
                    "errors=%s response_chars=%d",
                    getattr(repair_error, "errors", lambda: str(repair_error))(),
                    len(repaired),
                )
                raise

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
        return _provider_schema(schema)


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
