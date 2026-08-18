"""Retry boundary for transient read failures from the PlaceChecker catalog."""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg

from app.modules.place_checker.errors import PlaceCatalogUnavailableError


_TRANSIENT_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    ConnectionError,
    OSError,
    TimeoutError,
)


class PostgresCatalogRetryMixin:
    async def _fetch(self, sql: str, *arguments: Any):
        """Run a read query once more after recycling a dropped pool."""
        for attempt in range(2):
            pool = await self._get_pool()
            try:
                return await pool.fetch(sql, *arguments)
            except _TRANSIENT_ERRORS as exc:
                await self._discard_pool(pool)
                if attempt == 1:
                    raise PlaceCatalogUnavailableError(
                        "PlaceChecker PostgreSQL catalog is temporarily unavailable."
                    ) from exc
                await asyncio.sleep(0.05)
        raise RuntimeError("unreachable PostgreSQL retry state")

    async def _discard_pool(self, pool) -> None:
        async with self._pool_lock:
            if self._pool is not pool:
                return
            self._pool = None
            terminate = getattr(pool, "terminate", None)
            if terminate is not None:
                terminate()
                return
            close = getattr(pool, "close", None)
            if close is not None:
                await close()


async def fetch_catalog_rows(owner, sql: str, *arguments: Any):
    """Use the retry boundary when available, with a test-friendly fallback."""
    fetch = getattr(owner, "_fetch", None)
    if fetch is not None:
        return await fetch(sql, *arguments)
    pool = await owner._get_pool()
    return await pool.fetch(sql, *arguments)
