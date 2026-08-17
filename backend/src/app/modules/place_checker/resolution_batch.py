"""Chunked resolution orchestration for batch-capable search tools."""

from __future__ import annotations

import asyncio


RESOLUTION_BATCH_SIZE = 10


class EntityResolutionBatchMixin:
    async def _resolve_candidates(self, candidates, context):
        search_many = getattr(self.search_tool, "search_many", None)
        if search_many is None:
            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def bounded(index, candidate):
                async with semaphore:
                    return await self._resolve_one(index, candidate, context)

            return list(await asyncio.gather(*(
                bounded(index, candidate)
                for index, candidate in enumerate(candidates)
            )))

        chunks = [
            list(enumerate(candidates))[offset : offset + RESOLUTION_BATCH_SIZE]
            for offset in range(0, len(candidates), RESOLUTION_BATCH_SIZE)
        ]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def resolve_chunk(chunk):
            requests = [self._build_request(candidate, context) for _, candidate in chunk]
            try:
                async with semaphore:
                    results = await search_many(requests)
            except Exception:
                return [
                    await self._resolve_one(index, candidate, context)
                    for index, candidate in chunk
                ]
            return [
                self._map_result(index, candidate, context, result)
                for (index, candidate), result in zip(chunk, results)
            ]

        resolved_chunks = await asyncio.gather(*(resolve_chunk(chunk) for chunk in chunks))
        return [item for chunk in resolved_chunks for item in chunk]
