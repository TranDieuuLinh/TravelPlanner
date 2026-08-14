"""Lazy async Postgres checkpointer adapter for the root LangGraph.

The optional dependency is imported only when a database URL is configured. This
keeps unit tests and development without Postgres on the existing in-memory
provider while making the durable path explicit and observable.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)


class LazyAsyncPostgresCheckpointer(BaseCheckpointSaver):
    def __init__(self, database_url: str, *, serde=None) -> None:
        super().__init__(serde=serde)
        self.database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self._manager = None
        self._delegate = None
        self._lock = asyncio.Lock()

    async def _get_delegate(self):
        if self._delegate is None:
            async with self._lock:
                if self._delegate is None:
                    try:
                        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                    except ImportError as exc:
                        raise RuntimeError(
                            "Postgres checkpointer requires langgraph-checkpoint-postgres"
                        ) from exc
                    self._manager = AsyncPostgresSaver.from_conn_string(
                        self.database_url, serde=self.serde
                    )
                    self._delegate = await self._manager.__aenter__()
                    await self._delegate.setup()
        return self._delegate

    async def aget_tuple(self, config):
        return await (await self._get_delegate()).aget_tuple(config)

    async def alist(self, config, *, filter=None, before=None, limit=None) -> AsyncIterator[CheckpointTuple]:
        delegate = await self._get_delegate()
        async for item in delegate.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(self, config, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions):
        return await (await self._get_delegate()).aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = ""):
        return await (await self._get_delegate()).aput_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await (await self._get_delegate()).adelete_thread(thread_id)

    async def adelete_for_runs(self, run_ids: Sequence[str]) -> None:
        await (await self._get_delegate()).adelete_for_runs(run_ids)

    async def aprune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        # The upstream saver performs delta-aware pruning. Delegate rather than
        # deleting only the head row, which could break checkpoint reconstruction.
        await (await self._get_delegate()).aprune(thread_ids, strategy=strategy)

    async def aclose(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
            self._manager = None
            self._delegate = None
