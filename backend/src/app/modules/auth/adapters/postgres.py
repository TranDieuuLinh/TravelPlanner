import asyncio
import json
from datetime import datetime

from app.modules.auth.ports import SessionRecord, UserRecord
from app.modules.auth.security import new_password, verify_password


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


class PostgresUserRepository:
    """Owns auth_runtime_users and auth_runtime_sessions only."""

    def __init__(self, database_url: str, *, command_timeout: float = 15.0) -> None:
        self.database_url = _asyncpg_url(database_url)
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg  # type: ignore[import-untyped]
            except ImportError as exc:
                raise RuntimeError("asyncpg is required for PostgreSQL auth") from exc
            for attempt in range(5):
                try:
                    self._pool = await asyncpg.create_pool(
                        self.database_url,
                        command_timeout=self.command_timeout,
                        min_size=0,
                        max_size=1,
                    )
                    break
                except OSError:
                    # Compose may start the API just before Docker DNS/database
                    # is ready. Retry transient connection and name-resolution
                    # failures instead of turning the first request into 500.
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.5 * (2**attempt))
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def by_email(self, email: str) -> UserRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM auth_runtime_users WHERE email=$1", email.lower())
        return self._user(row) if row else None

    async def by_id(self, user_id: int) -> UserRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM auth_runtime_users WHERE id=$1", user_id)
        return self._user(row) if row else None

    async def create(
        self, email: str, full_name: str, password: str, role: str = "traveler"
    ) -> UserRecord:
        password_digest, password_salt = new_password(password)
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO auth_runtime_users
                   (email, full_name, password_hash, password_salt, role)
                   VALUES ($1,$2,$3,$4,$5) RETURNING *""",
                email.lower(), full_name, password_digest, password_salt, role,
            )
        return self._user(row)

    async def ensure_user(
        self, email: str, full_name: str, password: str, role: str
    ) -> UserRecord:
        existing = await self.by_email(email)
        if existing:
            return existing
        password_digest, password_salt = new_password(password)
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO auth_runtime_users
                   (email, full_name, password_hash, password_salt, role)
                   VALUES ($1,$2,$3,$4,$5) ON CONFLICT (email) DO NOTHING""",
                email.lower(), full_name, password_digest, password_salt, role,
            )
        return await self.by_email(email)  # type: ignore[return-value]

    async def check_password(self, user: UserRecord, password: str) -> bool:
        return verify_password(password, user.password_hash, user.password_salt)

    async def update_user(self, user_id: int, **changes: object) -> UserRecord:
        allowed = {
            "full_name": changes.get("full_name"), "avatar_url": changes.get("avatar_url"),
            "bio": changes.get("bio"), "travel_preferences": changes.get("travel_preferences"),
            "creator_status": changes.get("creator_status"),
            "creator_portfolio_urls": changes.get("creator_portfolio_urls"),
        }
        assignments: list[str] = []
        values: list[object] = [user_id]
        for column, value in allowed.items():
            if value is not None:
                values.append(json.dumps(value) if isinstance(value, list) else value)
                suffix = "::jsonb" if isinstance(value, list) else ""
                assignments.append(f"{column}=${len(values)}{suffix}")
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            if assignments:
                row = await connection.fetchrow(
                    f"UPDATE auth_runtime_users SET {', '.join(assignments)}, updated_at=now() WHERE id=$1 RETURNING *",
                    *values,
                )
            else:
                row = await connection.fetchrow("SELECT * FROM auth_runtime_users WHERE id=$1", user_id)
        return self._user(row)

    async def create_session(
        self, token_hash: str, user_id: int, csrf_token_hash: str, expires_at: datetime
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO auth_runtime_sessions
                   (token_hash, user_id, csrf_token_hash, expires_at)
                   VALUES ($1,$2,$3,$4)""",
                token_hash, user_id, csrf_token_hash, expires_at,
            )

    async def session_by_token(self, token_hash: str) -> SessionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT user_id, csrf_token_hash, expires_at
                   FROM auth_runtime_sessions WHERE token_hash=$1 AND expires_at > now()""",
                token_hash,
            )
            if row:
                await connection.execute(
                    "UPDATE auth_runtime_sessions SET last_used_at=now() WHERE token_hash=$1",
                    token_hash,
                )
        return SessionRecord(row["user_id"], row["csrf_token_hash"], row["expires_at"]) if row else None

    async def delete_session(self, token_hash: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM auth_runtime_sessions WHERE token_hash=$1", token_hash)

    @staticmethod
    def _user(row) -> UserRecord:
        return UserRecord(
            id=row["id"], email=row["email"], full_name=row["full_name"],
            password_hash=row["password_hash"], password_salt=row["password_salt"],
            role=row["role"], status=row["status"], avatar_url=row["avatar_url"],
            bio=row["bio"], travel_preferences=_json_value(row["travel_preferences"]) or [],
            creator_status=row["creator_status"],
            creator_portfolio_urls=_json_value(row["creator_portfolio_urls"]) or [],
            created_at=row["created_at"],
        )
