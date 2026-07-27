from app.integrations.llm.base import LLMClient


class StubLLMClient(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        return f"Draft travel profile generated from: {prompt}"
