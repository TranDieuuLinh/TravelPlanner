from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, TypeVar, cast

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import ensure_config

ResultT = TypeVar("ResultT")

_current_trace_callback: ContextVar[AsyncCallbackHandler | None] = ContextVar(
    "_current_trace_callback", default=None
)


def get_current_trace_callback() -> AsyncCallbackHandler | None:
    return _current_trace_callback.get()


def set_current_trace_callback(
    callback: AsyncCallbackHandler | None,
) -> Any:
    return _current_trace_callback.set(callback)


def reset_current_trace_callback(token: Any) -> None:
    try:
        _current_trace_callback.reset(token)
    except ValueError:
        # A service may finish a trace from a different asyncio task (for
        # example, a test calling asyncio.run around a synchronous setup).
        # ContextVar tokens are context-bound; clear only the current context
        # instead of allowing cleanup to break the request.
        _current_trace_callback.set(None)


async def traced_call(
    name: str,
    operation: Callable[[], Awaitable[ResultT]],
    *,
    kind: str = "provider",
    input_summary: Any = None,
    output_summary: Callable[[ResultT], Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ResultT:
    """Run an async capability as a bounded child span when callbacks exist.

    The runnable receives caller-supplied summaries so observability can record
    useful metrics. The Langfuse adapter redacts/truncates them and omits
    input/output entirely unless ``LANGFUSE_CAPTURE_INPUT_OUTPUT=true``;
    credentials are never passed to this function.
    """
    config = ensure_config()
    callbacks = config.get("callbacks")
    if not callbacks:
        ctx_cb = get_current_trace_callback()
        if ctx_cb is not None:
            callbacks = [ctx_cb]

    if not callbacks:
        return await operation()

    result: list[ResultT] = []

    async def invoke(_: Any) -> Any:
        value = await operation()
        result.append(value)
        return output_summary(value) if output_summary else None

    runnable = RunnableLambda(invoke).with_config(
        {
            "run_name": name,
            "tags": [f"trace_kind:{kind}"],
            "metadata": metadata or {},
            "callbacks": callbacks,
        }
    )
    await runnable.ainvoke(input_summary)
    return cast(ResultT, result[0])
