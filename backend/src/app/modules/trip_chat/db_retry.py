"""Small retry boundary for transient cloud PostgreSQL failures."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import asyncpg

T = TypeVar("T")


def is_transient_database_error(error: BaseException) -> bool:
    return isinstance(error, (
        asyncpg.PostgresConnectionError,
        asyncpg.InterfaceError,
        asyncpg.TooManyConnectionsError,
        ConnectionError,
        TimeoutError,
    ))


async def retry_transient_database(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
) -> T:
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            if not is_transient_database_error(exc):
                raise
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(0.2 * (2**attempt))
    raise RuntimeError("unreachable database retry state")
