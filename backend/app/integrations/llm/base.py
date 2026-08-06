from abc import ABC, abstractmethod
from dataclasses import dataclass


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
