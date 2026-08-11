from typing import Protocol

from app.shared.tools.search_places.contract import (
    AdministrativeArea,
    PlaceProviderCandidate,
)


class PlaceSearchProviderError(RuntimeError):
    code = "place_search_provider_error"


class PlaceSearchProviderTimeout(PlaceSearchProviderError):
    code = "place_search_provider_timeout"


class KnowledgeGraphPlaceSearch(Protocol):
    provider_name: str

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
    ) -> list[PlaceProviderCandidate]: ...


class ExternalPlaceSearch(Protocol):
    provider_name: str

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
    ) -> list[PlaceProviderCandidate]: ...

