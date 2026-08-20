import asyncio
import os
from pathlib import Path

import asyncpg


async def main() -> None:
    dsn = os.environ["TASK_DATABASE_URL"]
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(Path("migrations/027_trip_chat_suggestions.sql").read_text())
    finally:
        await conn.close()
    print("MIGRATION_APPLIED")


asyncio.run(main())
