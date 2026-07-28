from app.integrations.llm.base import LLMClient
from app.core.config import settings
from app.integrations.llm.provider import GeminiLLMClient, StubLLMClient


def get_llm_client() -> LLMClient:
    if settings.gemini_api_key:
        return GeminiLLMClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    return StubLLMClient()
