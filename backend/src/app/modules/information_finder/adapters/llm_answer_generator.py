import json
import logging
import time

from pydantic import ValidationError

from app.modules.information_finder.contract import GeneratedAnswer, RetrievedSource
from app.modules.information_finder.errors import (
    AnswerProviderError,
    AnswerProviderInvalidOutput,
    AnswerProviderQuotaExceeded,
    AnswerProviderRefusal,
    AnswerProviderTimeout,
    AnswerProviderUnauthorized,
)
from app.modules.information_finder.prompts import (
    ANSWER_SYSTEM_PROMPT,
    build_answer_prompt,
    build_answer_repair_prompt,
)
from app.shared.llm import (
    LlmClient,
    LlmError,
    LlmQuotaError,
    LlmRefusalError,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnauthorizedError,
)

logger = logging.getLogger(__name__)


def _provider_schema(value):
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key not in {
                "default",
                "minLength",
                "maxLength",
                "minItems",
                "maxItems",
            }
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value


class StructuredLlmAnswerGenerator:
    def __init__(
        self,
        client: LlmClient,
        *,
        max_output_tokens: int = 800,
        max_chars_per_source: int = 4000,
        max_total_source_chars: int = 12000,
    ) -> None:
        self.client = client
        self.max_output_tokens = max_output_tokens
        self.max_chars_per_source = max_chars_per_source
        self.max_total_source_chars = max_total_source_chars

    async def generate(
        self,
        query: str,
        sources: list[RetrievedSource],
    ) -> GeneratedAnswer:
        started = time.monotonic()
        error_code = "none"
        prompt = build_answer_prompt(
            query,
            sources,
            max_chars_per_source=self.max_chars_per_source,
            max_total_source_chars=self.max_total_source_chars,
        )
        return await self._generate_prompt(prompt, len(sources), started)

    async def generate_repair(
        self, query: str, sources: list[RetrievedSource], invalid_source_ids: list[str]
    ) -> GeneratedAnswer:
        started = time.monotonic()
        prompt = build_answer_repair_prompt(
            query,
            sources,
            invalid_source_ids,
            max_chars_per_source=self.max_chars_per_source,
            max_total_source_chars=self.max_total_source_chars,
        )
        return await self._generate_prompt(prompt, len(sources), started)

    async def _generate_prompt(self, prompt: str, source_count: int, started: float) -> GeneratedAnswer:
        error_code = "none"
        try:
            raw = await self.client.generate(
                prompt,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                temperature=0.0,
                max_output_tokens=self.max_output_tokens,
                response_json_schema=_provider_schema(
                    GeneratedAnswer.model_json_schema()
                ),
            )
            answer = GeneratedAnswer.model_validate(json.loads(raw))
        except LlmTimeoutError as exc:
            error_code = AnswerProviderTimeout.code
            raise AnswerProviderTimeout("LLM answer request timed out") from exc
        except LlmUnauthorizedError as exc:
            error_code = AnswerProviderUnauthorized.code
            raise AnswerProviderUnauthorized("LLM credentials were rejected") from exc
        except LlmQuotaError as exc:
            error_code = AnswerProviderQuotaExceeded.code
            raise AnswerProviderQuotaExceeded("LLM quota was exceeded") from exc
        except LlmRefusalError as exc:
            error_code = AnswerProviderRefusal.code
            raise AnswerProviderRefusal("LLM refused to answer") from exc
        except (
            LlmResponseError,
            json.JSONDecodeError,
            TypeError,
            ValidationError,
        ) as exc:
            error_code = AnswerProviderInvalidOutput.code
            raise AnswerProviderInvalidOutput(
                "LLM returned invalid structured output"
            ) from exc
        except LlmError as exc:
            error_code = AnswerProviderError.code
            raise AnswerProviderError("LLM answer generation failed") from exc
        finally:
            logger.info(
                "information_finder_answer_call source_count=%d latency_ms=%d error_code=%s",
                source_count,
                int((time.monotonic() - started) * 1000),
                error_code,
            )
        return answer
