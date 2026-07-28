from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMImageInput:
    data: bytes
    mime_type: str


class LLMClient(ABC):
    @abstractmethod
    async def generate_profile_plan(self, prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raise NotImplementedError

    async def generate_text_from_images(
        self,
        system_prompt: str,
        user_text: str,
        images: list[LLMImageInput],
        *,
        model: str | None = None,
    ) -> str:
        raise RuntimeError("The configured LLM provider does not support image input.")
