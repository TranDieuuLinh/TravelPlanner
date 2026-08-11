from collections.abc import Mapping
from typing import Any, Protocol


class LangfuseProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class LangfuseClient(Protocol):
    configured: bool

    async def get(
        self, resource: str, params: Mapping[str, str | int | None]
    ) -> dict[str, Any]: ...

    async def ingest(self, payload: dict[str, Any]) -> None: ...
