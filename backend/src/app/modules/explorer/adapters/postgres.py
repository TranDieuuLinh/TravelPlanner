def asyncpg_dsn(database_url: str) -> str:
    for scheme in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql://", 1)
    return database_url
