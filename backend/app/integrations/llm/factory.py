from functools import lru_cache

from app.integrations.llm.base import LLMClient
from app.core.config import settings
from app.integrations.llm.provider import GeminiLLMClient, StubLLMClient


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    if settings.gemini_api_key:
        return GeminiLLMClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            min_interval_seconds=settings.gemini_min_interval_seconds,
        )
    return StubLLMClient()
