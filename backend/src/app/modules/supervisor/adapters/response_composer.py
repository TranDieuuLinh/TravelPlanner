import json

from app.modules.supervisor.prompts import RESPONSE_COMPOSER_SYSTEM_PROMPT
from app.shared.llm import LlmClient


class GeminiResponseComposer:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 512) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def compose(self, payload: dict) -> str:
        return await self._client.generate(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            system_prompt=RESPONSE_COMPOSER_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
        )
