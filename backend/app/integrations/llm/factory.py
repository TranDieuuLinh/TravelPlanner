import logging
from functools import lru_cache

from app.core.config import settings
from app.integrations.llm.base import LLMClient
from app.integrations.llm.provider import GeminiLLMClient, StubLLMClient
from app.integrations.llm.tracing import TracingLLMClient, configure_langfuse

logger = logging.getLogger(__name__)


def _trace(client: LLMClient, *, provider: str, model: str | None) -> LLMClient:
    if not (
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):
        return client
    if not configure_langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.langfuse_environment,
    ):
        logger.warning("Langfuse tracing could not be configured")
        return client
    return TracingLLMClient(client, provider=provider, model=model)


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    if settings.gemini_api_key:
        return _trace(
            GeminiLLMClient(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                min_interval_seconds=settings.gemini_min_interval_seconds,
            ),
            provider="gemini",
            model=settings.gemini_model,
        )
    return _trace(StubLLMClient(), provider="stub", model="stub")


@lru_cache(maxsize=1)
def get_ocr_llm_client() -> LLMClient:
    if settings.gemini_ocr_key_pool:
        return _trace(
            GeminiLLMClient(
                api_key=settings.gemini_ocr_key_pool,
                model=settings.gemini_image_ocr_model,
                min_interval_seconds=settings.gemini_min_interval_seconds,
            ),
            provider="gemini",
            model=settings.gemini_image_ocr_model,
        )
    return _trace(StubLLMClient(), provider="stub", model="stub")
