import asyncio

import pytest

from app.bootstrap import create_supervisor_service
from app.core.config import Settings
from app.modules.supervisor.contract import SupervisorInput
from app.shared.llm import LlmConfigurationError


def test_rules_provider_is_offline_and_does_not_require_api_key():
    service = create_supervisor_service(
        Settings(supervisor_classifier_provider="rules")
    )
    decision = asyncio.run(service.decide(SupervisorInput(message="Xin chào")))
    assert decision.route == "finish"


def test_gemini_provider_without_key_fails_at_composition():
    with pytest.raises(LlmConfigurationError, match="GEMINI_API_KEY"):
        create_supervisor_service(
            Settings(supervisor_classifier_provider="gemini", gemini_api_key=None)
        )
