from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import ensure_config


ResultT = TypeVar("ResultT")


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

    The runnable only receives and returns caller-supplied summaries. Provider
    payloads, credentials, prompts, and full responses stay outside tracing.
    """
    config = ensure_config()
    if not config.get("callbacks"):
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
        }
    )
    await runnable.ainvoke(input_summary)
    return cast(ResultT, result[0])
