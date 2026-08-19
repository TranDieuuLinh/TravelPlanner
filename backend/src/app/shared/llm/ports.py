from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class InlineMedia:
    mime_type: str
    data_base64: str


class LlmClient(Protocol):
    async def generate(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        response_json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate text from a user prompt."""

    async def generate_media(
        self,
        user_prompt: str,
        media: list[InlineMedia],
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate text from a prompt plus inline image or audio data."""
