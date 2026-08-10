"""Privacy-safe Langfuse generations around the provider-neutral LLM client.

Raw prompts, user payloads, image bytes and model output are deliberately not
exported. Observations contain operational summaries, provider/model identity
and the exact token usage returned by the provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from inspect import iscoroutinefunction, signature
from functools import lru_cache, wraps
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from app.integrations.llm.base import (
    GroundedStructuredResult,
    LLMClient,
    LLMImageInput,
    LLMUsage,
)

try:
    from langfuse.decorators import langfuse_context, observe
except ImportError:  # pragma: no cover - optional when tracing is disabled
    langfuse_context = None  # type: ignore[assignment]
    observe = None  # type: ignore[assignment]

P = ParamSpec("P")
T = TypeVar("T")
_configured = False
_MAX_TRACE_STRING_CHARACTERS = 50_000
_MAX_PROMPT_PREVIEW_CHARACTERS = 2_000
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|access[_-]?token|"
    r"refresh[_-]?token|user[_-]?id|email|phone)",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){9,15}(?!\d)")
_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:sk|pk|AIza|Bearer)[-_A-Za-z0-9.]{12,}\b",
    re.IGNORECASE,
)


def _redact_text(value: str) -> str:
    value = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    value = _PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    value = _CREDENTIAL_PATTERN.sub("[REDACTED_CREDENTIAL]", value)
    if len(value) > _MAX_TRACE_STRING_CHARACTERS:
        omitted = len(value) - _MAX_TRACE_STRING_CHARACTERS
        return value[:_MAX_TRACE_STRING_CHARACTERS] + (
            f"… [truncated {omitted} characters]"
        )
    return value


def _sanitize_trace_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 20:
        return "[MAX_DEPTH_REACHED]"
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _SENSITIVE_KEY_PATTERN.search(str(key))
                else _sanitize_trace_value(item, depth=depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_trace_value(item, depth=depth + 1)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        fields = asdict(value)
        return {
            "type": type(value).__name__,
            "fields": {
                str(key): _application_input_value(item)
                for key, item in fields.items()
                if not _SENSITIVE_KEY_PATTERN.search(str(key))
            },
        }
    return _redact_text(str(value))


def _prompt_preview(value: str) -> str:
    """Return a useful excerpt while never exporting the complete prompt."""

    if len(value) < 2:
        return "[PROMPT_TOO_SHORT_TO_PREVIEW]"
    preview_length = min(
        _MAX_PROMPT_PREVIEW_CHARACTERS,
        max(1, len(value) // 2),
    )
    preview = _redact_text(value[:preview_length])
    return preview + f"… [omitted {len(value) - preview_length} characters]"


def _detailed_output(result: Any) -> Any:
    if isinstance(result, GroundedStructuredResult):
        return _sanitize_trace_value(
            {
                "text": _parse_json_or_text(result.text),
                "sources": [
                    {"title": source.title, "uri": source.uri}
                    for source in result.sources
                ],
                "searchQueries": list(result.search_queries),
            }
        )
    if isinstance(result, str):
        return _sanitize_trace_value(_parse_json_or_text(result))
    return _sanitize_trace_value(result)


def _parse_json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


@lru_cache(maxsize=1)
def configure_langfuse(
    *,
    public_key: str,
    secret_key: str,
    host: str,
    environment: str,
) -> bool:
    """Configure the v2 decorator client before its first observed call."""

    global _configured
    if langfuse_context is None:
        return False
    try:
        langfuse_context.configure(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            environment=environment,
            enabled=True,
        )
    except Exception:
        # Observability must never prevent the Planner from starting.
        return False
    _configured = True
    return True


def shutdown_langfuse() -> None:
    """Drain queued observations during application shutdown."""

    if not _configured or langfuse_context is None:
        return
    try:
        langfuse_context.client_instance.shutdown()
    except Exception:
        # Shutdown telemetry is best effort and must not break app teardown.
        return


def _trace_method(
    name: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorator(function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        if observe is None:
            return function

        @wraps(function)
        async def instrumented(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await function(*args, **kwargs)
            except BaseException as exc:
                _record_observation_failure(name, exc)
                raise

        return observe(
            name=name,
            as_type="generation",
            capture_input=False,
            capture_output=False,
        )(instrumented)

    return decorator


def observe_external_generation(
    name: str,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Observe provider calls outside LLMClient only after configuration.

    URL media extraction has provider-specific adapters that cannot use the
    text-only LLMClient contract. This wrapper keeps those calls traceable while
    avoiding SDK initialization when Langfuse is disabled.
    """

    def decorator(function: Callable[P, T]) -> Callable[P, T]:
        observed = (
            observe(
                name=name,
                as_type="generation",
                capture_input=False,
                capture_output=False,
            )(function)
            if observe is not None
            else function
        )

        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            target = observed if _configured else function
            return target(*args, **kwargs)

        return wrapper

    return decorator


def _application_input_value(value: Any) -> Any:
    """Describe workflow inputs without exporting raw prompts or user payloads."""

    if isinstance(value, str):
        return {"type": "str", "characters": len(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "bytes", "bytes": len(value)}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        safe_keys = [
            str(key)
            for key in value
            if not _SENSITIVE_KEY_PATTERN.search(str(key))
        ]
        return {
            "type": "dict",
            "items": len(value),
            "keys": sorted(safe_keys)[:100],
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return {
            "type": type(value).__name__,
            "items": len(value),
            "itemTypes": sorted({type(item).__name__ for item in value})[:20],
        }
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            fields = model_dump(mode="json", by_alias=True)
        except (TypeError, ValueError):
            fields = model_dump()
        return {
            "type": type(value).__name__,
            "fields": sorted(str(key) for key in fields)[:100],
        }
    return {"type": type(value).__name__}


def _application_input_summary(function: Callable[..., Any], args: tuple, kwargs: dict) -> dict:
    try:
        bound = signature(function).bind_partial(*args, **kwargs)
        values = bound.arguments
    except (TypeError, ValueError):
        values = {"args": args, "kwargs": kwargs}
    return {
        name: _application_input_value(value)
        for name, value in values.items()
        if name not in {"self", "cls"}
        and not _SENSITIVE_KEY_PATTERN.search(name)
    }


def _application_output_detail(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            value = model_dump(mode="json", by_alias=True)
        except (TypeError, ValueError):
            value = model_dump()
    elif isinstance(value, tuple):
        value = [_application_output_detail(item) for item in value]
    return _sanitize_trace_value(value)


def _begin_application_span(name: str, input_summary: dict[str, Any]) -> None:
    if langfuse_context is None:
        return
    metadata = {"kind": "application", "operation": name}
    try:
        langfuse_context.update_current_observation(
            input=input_summary,
            metadata=metadata,
        )
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(
            input=input_summary,
            metadata=metadata,
        )
    except Exception:
        return


def _finish_application_span(name: str, result: Any) -> None:
    if langfuse_context is None:
        return
    output = _application_output_detail(result)
    metadata = {"kind": "application", "operation": name}
    try:
        langfuse_context.update_current_observation(
            output=output,
            metadata=metadata,
        )
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(output=output, metadata=metadata)
    except Exception:
        return


def _fail_application_span(name: str, exc: BaseException) -> None:
    if langfuse_context is None:
        return
    metadata = {
        "kind": "application",
        "operation": name,
        "status": "error",
        "errorType": type(exc).__name__,
    }
    output = {"status": "error", "errorType": type(exc).__name__}
    try:
        langfuse_context.update_current_observation(
            output=output,
            metadata=metadata,
        )
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(output=output, metadata=metadata)
    except Exception:
        return


def _record_observation_failure(name: str, exc: BaseException) -> None:
    """Keep failed generation nodes useful without exporting error messages."""

    if langfuse_context is None:
        return
    output = {"status": "error", "errorType": type(exc).__name__}
    metadata = {
        "operation": name,
        "status": "error",
        "errorType": type(exc).__name__,
    }
    try:
        langfuse_context.update_current_observation(
            output=output,
            metadata=metadata,
        )
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(output=output, metadata=metadata)
    except Exception:
        return


def observe_application(
    name: str,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Create a privacy-safe application span around sync or async workflows."""

    def decorator(function: Callable[P, T]) -> Callable[P, T]:
        if iscoroutinefunction(function):
            @wraps(function)
            async def instrumented_async(*args: P.args, **kwargs: P.kwargs) -> Any:
                _begin_application_span(
                    name,
                    _application_input_summary(function, args, kwargs),
                )
                try:
                    result = await function(*args, **kwargs)
                except BaseException as exc:
                    _fail_application_span(name, exc)
                    raise
                _finish_application_span(name, result)
                return result

            observed = (
                observe(name=name, capture_input=False, capture_output=False)(
                    instrumented_async
                )
                if observe is not None
                else instrumented_async
            )

            @wraps(function)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                target = observed if _configured else function
                return await target(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(function)
        def instrumented_sync(*args: P.args, **kwargs: P.kwargs) -> T:
            _begin_application_span(
                name,
                _application_input_summary(function, args, kwargs),
            )
            try:
                result = function(*args, **kwargs)
            except BaseException as exc:
                _fail_application_span(name, exc)
                raise
            _finish_application_span(name, result)
            return result

        observed = (
            observe(name=name, capture_input=False, capture_output=False)(
                instrumented_sync
            )
            if observe is not None
            else instrumented_sync
        )

        @wraps(function)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            target = observed if _configured else function
            return target(*args, **kwargs)

        return sync_wrapper

    return decorator


def _begin_generation(
    *,
    provider: str,
    model: str | None,
    operation: str,
    input_summary: dict[str, Any],
) -> None:
    if langfuse_context is None:
        return
    try:
        langfuse_context.update_current_observation(
            input=input_summary,
            model=model,
            metadata={"provider": provider, "operation": operation},
        )
    except Exception:
        pass
    try:
        # A top-level `@observe(as_type="generation")` in Langfuse v2 creates
        # a wrapper TRACE plus a child GENERATION. Keep both useful when the
        # user selects either node in the UI.
        langfuse_context.update_current_trace(
            input=input_summary,
            metadata={"provider": provider, "operation": operation},
        )
    except Exception:
        return


def begin_external_generation(
    *,
    provider: str,
    model: str | None,
    operation: str,
    input_summary: dict[str, Any],
) -> None:
    if not _configured:
        return
    _begin_generation(
        provider=provider,
        model=model,
        operation=operation,
        input_summary=input_summary,
    )


def _finish_generation(
    *,
    provider: str,
    configured_model: str | None,
    operation: str,
    result: Any,
    usage: LLMUsage | None,
) -> None:
    if langfuse_context is None:
        return
    if isinstance(result, GroundedStructuredResult):
        output_detail = _detailed_output(result)
    else:
        output_detail = _detailed_output(result)
    metadata: dict[str, Any] = {
        "provider": provider,
        "operation": operation,
        "outputType": type(result).__name__,
    }
    update: dict[str, Any] = {
        "output": output_detail,
        "model": usage.model if usage else configured_model,
        "metadata": metadata,
    }
    if usage is not None:
        usage_details = {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "total": usage.total_tokens,
        }
        update["usage_details"] = usage_details
        # Langfuse server v2 persists its legacy token columns from `usage`.
        # Keep both representations while this project intentionally runs the
        # v2 server/SDK; the values are identical and are not double-counted.
        update["usage"] = {**usage_details, "unit": "TOKENS"}
        metadata["providerUsage"] = usage.details
    try:
        langfuse_context.update_current_observation(**update)
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(
            output=output_detail,
            metadata=metadata,
        )
    except Exception:
        return


def finish_external_gemini_generation(
    *,
    operation: str,
    configured_model: str,
    response: dict,
    output_summary: dict[str, Any],
) -> None:
    """Attach one raw Gemini REST response's safe telemetry to a generation."""

    if not _configured or langfuse_context is None:
        return
    # Local import avoids coupling the provider module's import path back to
    # tracing while sharing the exact same token accounting implementation.
    from app.integrations.llm.provider import GeminiLLMClient

    usage = GeminiLLMClient._usage_from_response(response, configured_model)
    metadata: dict[str, Any] = {
        "provider": "gemini",
        "operation": operation,
    }
    update: dict[str, Any] = {
        "output": output_summary,
        "model": usage.model if usage else configured_model,
        "metadata": metadata,
    }
    if usage is not None:
        usage_details = {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "total": usage.total_tokens,
        }
        update["usage_details"] = usage_details
        update["usage"] = {**usage_details, "unit": "TOKENS"}
        metadata["providerUsage"] = usage.details
    try:
        langfuse_context.update_current_observation(**update)
    except Exception:
        pass
    try:
        langfuse_context.update_current_trace(
            output=output_summary,
            metadata=metadata,
        )
    except Exception:
        return


class TracingLLMClient(LLMClient):
    """Decorate an LLM client without changing its provider contract."""

    def __init__(self, client: LLMClient, *, provider: str, model: str | None) -> None:
        self._client = client
        self._provider = provider
        self._model = model

    def _begin(self, operation: str, input_summary: dict[str, Any]) -> None:
        _begin_generation(
            provider=self._provider,
            model=self._model,
            operation=operation,
            input_summary=input_summary,
        )

    def _finish(self, operation: str, result: Any) -> None:
        _finish_generation(
            provider=self._provider,
            configured_model=self._model,
            operation=operation,
            result=result,
            usage=self._client.consume_last_usage(),
        )

    @_trace_method("llm.generate_profile_plan")
    async def generate_profile_plan(self, prompt: str) -> str:
        operation = "generate_profile_plan"
        self._begin(
            operation,
            {
                "promptCharacters": len(prompt),
                "promptPreview": _prompt_preview(prompt),
            },
        )
        result = await self._client.generate_profile_plan(prompt)
        self._finish(operation, result)
        return result

    @_trace_method("llm.generate_json")
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        operation = "generate_json"
        self._begin(
            operation,
            {
                "systemPromptCharacters": len(system_prompt),
                "userPayloadCharacters": len(user_payload),
                "systemPromptPreview": _prompt_preview(system_prompt),
                "userPayloadPreview": _prompt_preview(user_payload),
            },
        )
        result = await self._client.generate_json(system_prompt, user_payload)
        self._finish(operation, result)
        return result

    @_trace_method("llm.generate_structured_json")
    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        operation = "generate_structured_json"
        self._begin(
            operation,
            {
                "systemPromptCharacters": len(system_prompt),
                "userPayloadCharacters": len(user_payload),
                "systemPromptPreview": _prompt_preview(system_prompt),
                "userPayloadPreview": _prompt_preview(user_payload),
                "responseSchemaProvided": bool(response_schema),
                "responseSchemaPropertyCount": len(
                    response_schema.get("properties", {})
                ),
                "responseSchema": _sanitize_trace_value(response_schema),
            },
        )
        result = await self._client.generate_structured_json(
            system_prompt,
            user_payload,
            response_schema=response_schema,
        )
        self._finish(operation, result)
        return result

    @_trace_method("llm.generate_text_from_images")
    async def generate_text_from_images(
        self,
        system_prompt: str,
        user_text: str,
        images: list[LLMImageInput],
        *,
        model: str | None = None,
    ) -> str:
        operation = "generate_text_from_images"
        selected_model = model or self._model
        _begin_generation(
            provider=self._provider,
            model=selected_model,
            operation=operation,
            input_summary={
                "systemPromptCharacters": len(system_prompt),
                "userTextCharacters": len(user_text),
                "systemPromptPreview": _prompt_preview(system_prompt),
                "userTextPreview": _prompt_preview(user_text),
                "imageCount": len(images),
                "imageBytes": sum(len(image.data) for image in images),
                "imageMimeTypes": sorted({image.mime_type for image in images}),
            },
        )
        result = await self._client.generate_text_from_images(
            system_prompt,
            user_text,
            images,
            model=model,
        )
        _finish_generation(
            provider=self._provider,
            configured_model=selected_model,
            operation=operation,
            result=result,
            usage=self._client.consume_last_usage(),
        )
        return result

    @_trace_method("llm.generate_grounded_structured_json")
    async def generate_grounded_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> GroundedStructuredResult:
        operation = "generate_grounded_structured_json"
        self._begin(
            operation,
            {
                "systemPromptCharacters": len(system_prompt),
                "userPayloadCharacters": len(user_payload),
                "systemPromptPreview": _prompt_preview(system_prompt),
                "userPayloadPreview": _prompt_preview(user_payload),
                "responseSchemaProvided": bool(response_schema),
                "responseSchemaPropertyCount": len(
                    response_schema.get("properties", {})
                ),
                "responseSchema": _sanitize_trace_value(response_schema),
                "groundedSearch": True,
            },
        )
        result = await self._client.generate_grounded_structured_json(
            system_prompt,
            user_payload,
            response_schema=response_schema,
        )
        self._finish(operation, result)
        return result
