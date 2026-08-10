from typing import Protocol


class LlmClient(Protocol):
    async def generate(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate text from a user prompt."""
