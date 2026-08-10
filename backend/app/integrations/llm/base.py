from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMImageInput:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class GroundingSource:
    title: str
    uri: str


@dataclass(frozen=True)
class GroundedStructuredResult:
    text: str
    sources: tuple[GroundingSource, ...]
    search_queries: tuple[str, ...] = ()


@dataclass(frozen=True)
class LLMUsage:
    """Provider usage for the most recent call in the current async context."""

    model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    details: dict[str, Any]


class LLMClient(ABC):
    @abstractmethod
    async def generate_profile_plan(self, prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raise NotImplementedError

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        return await self.generate_json(system_prompt, user_payload)

    async def generate_text_from_images(
        self,
        system_prompt: str,
        user_text: str,
        images: list[LLMImageInput],
        *,
        model: str | None = None,
    ) -> str:
        raise RuntimeError("The configured LLM provider does not support image input.")

    async def generate_grounded_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> GroundedStructuredResult:
        raise RuntimeError(
            "The configured LLM provider does not support grounded search."
        )

    def consume_last_usage(self) -> LLMUsage | None:
        """Return provider telemetry without changing generation contracts.

        Implementations that expose usage must isolate it per async context and
        clear it when consumed so concurrent requests cannot leak telemetry into
        one another.
        """

        return None
