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


@lru_cache(maxsize=1)
def get_ocr_llm_client() -> LLMClient:
    if settings.gemini_ocr_key_pool:
        return GeminiLLMClient(
            api_key=settings.gemini_ocr_key_pool,
            model=settings.gemini_image_ocr_model,
            min_interval_seconds=settings.gemini_min_interval_seconds,
        )
    return StubLLMClient()
