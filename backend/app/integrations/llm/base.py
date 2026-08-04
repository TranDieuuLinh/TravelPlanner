from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def generate_profile_plan(self, prompt: str) -> str:
        raise NotImplementedError
