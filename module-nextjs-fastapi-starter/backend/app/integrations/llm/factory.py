from app.integrations.llm.base import LLMClient
from app.integrations.llm.provider import StubLLMClient


def get_llm_client() -> LLMClient:
    return StubLLMClient()
