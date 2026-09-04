from typing import Protocol

from app.modules.place_checker.subplaces.contract import (
    SubplaceGroup,
    SubplaceNoteRequest,
)


class SubplaceCatalog(Protocol):
    async def list_subplaces(
        self,
        parent_place_ids: list[str],
        *,
        per_parent_limit: int = 50,
    ) -> list[SubplaceGroup]: ...


class SubplaceNoteGenerator(Protocol):
    async def generate_many(
        self,
        requests: list[SubplaceNoteRequest],
    ) -> dict[str, str]: ...
