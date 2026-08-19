import pytest

from app.bootstrap import create_answer_generator
from app.core.config import Settings
from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
)
from app.modules.information_finder.adapters.llm_answer_generator import (
    StructuredLlmAnswerGenerator,
)
from app.shared.llm import LlmConfigurationError


def test_gemini_answer_provider_requires_shared_client_api_key() -> None:
    settings = Settings(
        information_finder_answer_provider="gemini",
        gemini_api_key=None,
    )
    with pytest.raises(LlmConfigurationError):
        create_answer_generator(settings)


def test_development_extractive_provider_needs_no_network_configuration() -> None:
    settings = Settings(
        information_finder_answer_provider="extractive",
        gemini_api_key=None,
    )
    assert isinstance(create_answer_generator(settings), ExtractiveAnswerGenerator)


def test_gemini_provider_uses_shared_llm_client() -> None:
    class Client:
        async def generate(self, user_prompt, **kwargs):
            return "{}"

    settings = Settings(information_finder_answer_provider="gemini")
    assert isinstance(
        create_answer_generator(settings, Client()), StructuredLlmAnswerGenerator
    )
