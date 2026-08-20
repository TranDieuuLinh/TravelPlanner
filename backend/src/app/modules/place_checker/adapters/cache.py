from time import monotonic

from app.modules.place_checker.contract import AdmResolution
from app.modules.place_checker.ports import (
    AdmResolver,
    NamedPlaceSearchTool,
    PlaceMetadataRepository,
)
from app.modules.place_checker.resolution.contract import PlaceMetadata
from app.shared.tools.search_places import PlaceSearchRequest, PlaceSearchResult


class CachingAdmResolver:
    def __init__(self, resolver: AdmResolver, *, ttl_seconds: int = 3600) -> None:
        self.resolver = resolver
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, tuple[float, AdmResolution]] = {}

    async def resolve(self, input_name: str) -> AdmResolution:
        key = input_name.casefold().strip()
        cached = self.cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
        result = await self.resolver.resolve(input_name)
        self.cache[key] = (monotonic() + self.ttl_seconds, result)
        return result


class CachingNamedPlaceSearchTool:
    def __init__(
        self,
        search_tool: NamedPlaceSearchTool,
        *,
        ttl_seconds: int = 900,
        max_entries: int = 1000,
    ) -> None:
        self.search_tool = search_tool
        self.ttl_seconds = ttl_seconds
        self.max_entries = max(1, max_entries)
        self.cache: dict[str, tuple[float, PlaceSearchResult]] = {}

    async def search(self, request: PlaceSearchRequest) -> PlaceSearchResult:
        key = request.model_dump_json(exclude_none=True)
        cached = self.cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
        result = await self.search_tool.search(request)
        if result.status not in {"provider_error"}:
            self._make_room()
            self.cache[key] = (monotonic() + self.ttl_seconds, result)
        return result

    def _make_room(self) -> None:
        while len(self.cache) >= self.max_entries:
            self.cache.pop(next(iter(self.cache)))


class CachingPlaceMetadataRepository:
    def __init__(
        self,
        repository: PlaceMetadataRepository,
        *,
        ttl_seconds: int = 900,
        max_entries: int = 5000,
    ) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self.max_entries = max(1, max_entries)
        self.cache: dict[str, tuple[float, PlaceMetadata]] = {}

    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]:
        now = monotonic()
        result = {
            place_id: cached[1]
            for place_id in place_ids
            if (cached := self.cache.get(place_id)) and cached[0] > now
        }
        missing = [place_id for place_id in place_ids if place_id not in result]
        if missing:
            loaded = await self.repository.get_many(missing)
            for place_id, metadata in loaded.items():
                self._make_room()
                self.cache[place_id] = (now + self.ttl_seconds, metadata)
            result.update(loaded)
        return result

    def _make_room(self) -> None:
        while len(self.cache) >= self.max_entries:
            self.cache.pop(next(iter(self.cache)))
