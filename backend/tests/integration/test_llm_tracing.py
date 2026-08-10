from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.integrations.llm.base import LLMClient, LLMUsage
from app.integrations.llm import tracing
from app.integrations.llm.tracing import (
    TracingLLMClient,
    _application_input_summary,
    _application_output_detail,
    _detailed_output,
    _fail_application_span,
)


class _FakeLLM(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        return "profile"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        return '{"ok": true}'

    def consume_last_usage(self) -> LLMUsage | None:
        return LLMUsage(
            model="gemini-test-version",
            input_tokens=12,
            output_tokens=7,
            total_tokens=19,
            details={"thinkingTokens": 2},
        )


class _FakeLangfuseContext:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_current_observation(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def update_current_trace(self, **kwargs: Any) -> None:
        self.updates.append({"trace": kwargs})


def test_tracing_client_records_generation_usage_without_private_payload(
    monkeypatch,
) -> None:
    context = _FakeLangfuseContext()
    monkeypatch.setattr(tracing, "langfuse_context", context)
    client = TracingLLMClient(_FakeLLM(), provider="fake", model="test-model")

    # Bypass the already-applied SDK decorator so this test only exercises our
    # enrichment and never exports a real test observation.
    method = getattr(TracingLLMClient.generate_json, "__wrapped__")
    result = asyncio.run(
        method(client, "private system prompt", "private user payload")
    )

    assert result == '{"ok": true}'
    assert context.updates[0] == {
        "input": {
            "systemPromptCharacters": 21,
            "userPayloadCharacters": 20,
            "systemPromptPreview": (
                "private sy… [omitted 11 characters]"
            ),
            "userPayloadPreview": (
                "private us… [omitted 10 characters]"
            ),
        },
        "model": "test-model",
        "metadata": {"provider": "fake", "operation": "generate_json"},
    }
    assert context.updates[1]["trace"]["input"] == context.updates[0]["input"]
    assert context.updates[2]["model"] == "gemini-test-version"
    assert context.updates[2]["usage_details"] == {
        "input": 12,
        "output": 7,
        "total": 19,
    }
    assert context.updates[2]["usage"] == {
        "input": 12,
        "output": 7,
        "total": 19,
        "unit": "TOKENS",
    }
    assert context.updates[2]["output"] == {"ok": True}
    assert context.updates[3]["trace"]["output"] == {"ok": True}
    serialized_updates = str(context.updates)
    assert "private system prompt" not in serialized_updates
    assert "private user payload" not in serialized_updates


def test_detailed_output_parses_json_and_redacts_sensitive_values() -> None:
    output = _detailed_output(
        '{"plan": {"name": "Hanoi trip"}, "email": "me@example.com", '
        '"note": "Call +84 912 345 678"}'
    )

    assert output["plan"] == {"name": "Hanoi trip"}
    assert output["email"] == "[REDACTED]"
    assert output["note"] == "Call [REDACTED_PHONE]"


def test_application_span_uses_structural_input_and_detailed_safe_output() -> None:
    def workflow(message: str, payload: dict[str, Any]) -> None:
        del message, payload

    summary = _application_input_summary(
        workflow,
        ("private trip request", {"destination": "Hanoi", "userId": 42}),
        {},
    )

    assert summary == {
        "message": {"type": "str", "characters": 20},
        "payload": {
            "type": "dict",
            "items": 2,
            "keys": ["destination"],
        },
    }
    assert "private trip request" not in str(summary)
    assert _application_output_detail(
        {"plan": {"name": "Hanoi trip"}, "email": "me@example.com"}
    ) == {
        "plan": {"name": "Hanoi trip"},
        "email": "[REDACTED]",
    }


def test_failed_application_span_has_non_null_safe_output(monkeypatch) -> None:
    context = _FakeLangfuseContext()
    monkeypatch.setattr(tracing, "langfuse_context", context)

    _fail_application_span("planner.test", ValueError("private error detail"))

    assert context.updates[0]["output"] == {
        "status": "error",
        "errorType": "ValueError",
    }
    assert context.updates[1]["trace"]["output"] == context.updates[0]["output"]
    assert "private error detail" not in str(context.updates)


def test_application_span_serializes_dataclass_output() -> None:
    @dataclass(frozen=True)
    class Result:
        total: int
        labels: tuple[str, ...]

    assert _application_output_detail(Result(total=2, labels=("a", "b"))) == {
        "total": 2,
        "labels": ["a", "b"],
    }
