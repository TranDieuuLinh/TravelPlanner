from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.modules.explorer.errors import ExplorerOperationError


T = TypeVar("T")


async def run_with_one_retry(operation: Callable[[], Awaitable[T]]) -> T:
    """Run one initial attempt and at most one retry for retryable failures."""

    for attempt in range(2):
        try:
            return await operation()
        except ExplorerOperationError as exc:
            if not exc.retryable or attempt == 1:
                raise
        except (TimeoutError, ConnectionError) as exc:
            if attempt == 1:
                raise ExplorerOperationError(
                    "SOURCE_UNAVAILABLE",
                    "Nguồn dữ liệu tạm thời không khả dụng.",
                    retryable=True,
                ) from exc
    raise AssertionError("retry loop must return or raise")
