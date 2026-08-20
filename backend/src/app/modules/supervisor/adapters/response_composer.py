import json
from pydantic import ValidationError
from app.modules.supervisor.contract import ComposedAnswer

from app.modules.supervisor.prompts import RESPONSE_COMPOSER_SYSTEM_PROMPT
from app.shared.llm import LlmClient


class GeminiResponseComposer:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 512) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def compose(self, payload: dict) -> ComposedAnswer:
        raw = await self._client.generate(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            system_prompt=RESPONSE_COMPOSER_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=ComposedAnswer.model_json_schema(),
        )
        try:
            return ComposedAnswer.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("Supervisor composer returned invalid structured output") from exc
