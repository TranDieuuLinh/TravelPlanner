import json

from app.modules.explorer.adapters.postgres import asyncpg_dsn
from app.modules.explorer.models import ExplorerDraft


class InMemorySourceExtractionCache:
    def __init__(self) -> None:
        self._items: dict[str, ExplorerDraft] = {}

    async def get(self, cache_key: str) -> ExplorerDraft | None:
        value = self._items.get(cache_key)
        return value.model_copy(deep=True) if value else None

    async def save(self, cache_key: str, draft: ExplorerDraft) -> None:
        self._items[cache_key] = draft.model_copy(deep=True)


class PostgresSourceExtractionCache:
    def __init__(
        self, database_url: str, *, namespace: str,
        ttl_seconds: float = 604_800, command_timeout: float = 15,
    ) -> None:
        self.database_url = asyncpg_dsn(database_url)
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.database_url, min_size=0, max_size=1,
                command_timeout=self.command_timeout,
            )
        return self._pool

    async def get(self, cache_key: str) -> ExplorerDraft | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """SELECT extraction FROM explorer_source_extraction_cache
               WHERE cache_key=$1 AND namespace=$2
                 AND updated_at >= now() - ($3 * interval '1 second')""",
            cache_key, self.namespace, self.ttl_seconds,
        )
        if row is None:
            return None
        value = row["extraction"]
        return ExplorerDraft.model_validate(json.loads(value) if isinstance(value, str) else value)

    async def save(self, cache_key: str, draft: ExplorerDraft) -> None:
        value = json.dumps(draft.model_dump(mode="json", by_alias=True), ensure_ascii=False)
        pool = await self._get_pool()
        await pool.execute(
            """INSERT INTO explorer_source_extraction_cache
               (cache_key, namespace, extraction, created_at, updated_at)
               VALUES ($1,$2,$3::json,now(),now())
               ON CONFLICT (cache_key) DO UPDATE SET
                 namespace=EXCLUDED.namespace, extraction=EXCLUDED.extraction,
                 updated_at=now()""",
            cache_key, self.namespace, value,
        )
