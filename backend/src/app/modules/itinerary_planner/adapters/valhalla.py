from __future__ import annotations

import asyncio
from collections import OrderedDict
from time import monotonic

import httpx

from app.shared.observability import traced_call
from app.modules.itinerary_planner.adapters.in_memory_matrix_cell import (
    InMemoryMatrixCellCache,
)
from app.modules.itinerary_planner.adapters.valhalla_matrix_batches import (
    full_matrix_batches,
    missing_matrix_batches,
    parse_matrix_cells,
)
from app.modules.itinerary_planner.ports import MatrixCellCache, MatrixCellCacheKey

from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    RoutingErrorCode,
    RoutingPhaseError,
    TravelMatrix,
)

DEFAULT_MAX_MATRIX_PAIRS = 2_500
DEFAULT_MATRIX_CONCURRENCY = 6
DEFAULT_MATRIX_BATCH_CACHE_ENTRIES = 128
DEFAULT_MATRIX_BATCH_CACHE_TTL_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 180.0
TARGETED_PAIR_CACHE_HIT_RATIO = 0.20


class ValhallaAdapter:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        provider_version: str = "unknown",
        max_matrix_pairs: int = DEFAULT_MAX_MATRIX_PAIRS,
        matrix_concurrency: int = DEFAULT_MATRIX_CONCURRENCY,
        matrix_batch_cache_entries: int = DEFAULT_MATRIX_BATCH_CACHE_ENTRIES,
        matrix_batch_cache_ttl_seconds: float = DEFAULT_MATRIX_BATCH_CACHE_TTL_SECONDS,
        matrix_cell_cache: MatrixCellCache | None = None,
    ) -> None:
        if max_matrix_pairs < 1:
            raise ValueError("max_matrix_pairs must be positive")
        if matrix_concurrency < 1:
            raise ValueError("matrix_concurrency must be positive")
        if matrix_batch_cache_entries < 1:
            raise ValueError("matrix_batch_cache_entries must be positive")
        if matrix_batch_cache_ttl_seconds <= 0:
            raise ValueError("matrix_batch_cache_ttl_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.provider_version = provider_version
        self.max_matrix_pairs = max_matrix_pairs
        self.matrix_concurrency = matrix_concurrency
        self.matrix_batch_cache_entries = matrix_batch_cache_entries
        self.matrix_batch_cache_ttl_seconds = matrix_batch_cache_ttl_seconds
        self.matrix_cell_cache = matrix_cell_cache or InMemoryMatrixCellCache()
        self._matrix_batch_cache: OrderedDict[
            tuple[str, tuple[str, ...], tuple[str, ...]],
            tuple[float, tuple[tuple[MatrixCell, ...], ...]],
        ] = OrderedDict()

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        return await traced_call(
            "valhalla.matrix",
            lambda: self._matrix(locations, profile),
            kind="tool",
            input_summary={
                "locationCount": len(locations),
                "profile": profile,
            },
            output_summary=lambda value: {
                "nodeCount": len(value.node_ids),
                "provider": value.provider,
                "providerVersion": value.provider_version,
                "logicalPairCount": value.logical_pair_count,
                "pairCacheHitCount": value.pair_cache_hit_count,
                "providerPairCount": value.provider_pair_count,
                "batchCount": value.batch_count,
            },
            metadata={"provider": "valhalla"},
        )

    async def _matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        semaphore = asyncio.Semaphore(self.matrix_concurrency)

        async def fetch(
            source_indexes: tuple[int, ...],
            sources: tuple[MatrixLocation, ...],
            target_indexes: tuple[int, ...],
            targets: tuple[MatrixLocation, ...],
        ) -> tuple[
            tuple[int, ...],
            tuple[int, ...],
            tuple[tuple[MatrixCell, ...], ...],
            bool,
        ]:
            cache_key = self._matrix_batch_cache_key(profile, sources, targets)
            cached = self._get_matrix_batch(cache_key)
            if cached is not None:
                return source_indexes, target_indexes, cached, False
            async with semaphore:
                cached = self._get_matrix_batch(cache_key)
                if cached is not None:
                    return source_indexes, target_indexes, cached, False
                response = await client.post(
                    f"{self.base_url}/sources_to_targets",
                    json={
                        "sources": [self._coordinate(item) for item in sources],
                        "targets": [self._coordinate(item) for item in targets],
                        "costing": self._costing(profile),
                        "units": "kilometers",
                    },
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            cells = parse_matrix_cells(
                response.json(), len(sources), len(targets)
            )
            self._put_matrix_batch(cache_key, cells)
            await self.matrix_cell_cache.put_many(
                {
                    self._matrix_cell_cache_key(profile, source, target): cell
                    for source, row in zip(sources, cells)
                    for target, cell in zip(targets, row)
                    if source.canonical_key != target.canonical_key
                }
            )
            return (
                source_indexes,
                target_indexes,
                cells,
                True,
            )

        try:
            rows: list[list[MatrixCell | None]] = [
                [None] * len(locations) for _ in locations
            ]
            for index in range(len(locations)):
                rows[index][index] = MatrixCell(0.0, 0.0, True)
            cell_key_by_pair = {
                (source_index, target_index): self._matrix_cell_cache_key(
                    profile, source, target
                )
                for source_index, source in enumerate(locations)
                for target_index, target in enumerate(locations)
                if source_index != target_index
            }
            cached_cells = await self.matrix_cell_cache.get_many(
                tuple(cell_key_by_pair.values())
            )
            for pair, key in cell_key_by_pair.items():
                if key in cached_cells:
                    rows[pair[0]][pair[1]] = cached_cells[key]
            logical_pair_count = len(cell_key_by_pair)
            pair_cache_hit_count = len(cached_cells)
            batches = missing_matrix_batches(
                locations,
                rows,
                max_pairs=self.max_matrix_pairs,
                targeted=(
                    logical_pair_count > 0
                    and pair_cache_hit_count / logical_pair_count
                    >= TARGETED_PAIR_CACHE_HIT_RATIO
                ),
            )
            results = await asyncio.gather(
                *(
                    fetch(source_indexes, sources, target_indexes, targets)
                    for source_indexes, sources, target_indexes, targets in batches
                )
            )
            provider_pair_count = 0
            provider_batch_count = 0
            for source_indexes, target_indexes, cells, provider_called in results:
                if provider_called:
                    provider_pair_count += len(source_indexes) * len(target_indexes)
                    provider_batch_count += 1
                for source_offset, row in enumerate(cells):
                    for target_offset, cell in enumerate(row):
                        rows[source_indexes[source_offset]][
                            target_indexes[target_offset]
                        ] = cell
            if any(cell is None for row in rows for cell in row):
                raise ValueError("matrix batches did not cover every source-target pair")
            return TravelMatrix(
                node_ids=tuple(item.node_id for item in locations),
                cells=tuple(
                    tuple(cell for cell in row if cell is not None) for row in rows
                ),
                profile=profile,
                provider="valhalla",
                provider_version=self.provider_version,
                logical_pair_count=logical_pair_count,
                pair_cache_hit_count=pair_cache_hit_count,
                provider_pair_count=provider_pair_count,
                batch_count=provider_batch_count,
            )
        except httpx.TimeoutException as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_timeout,
                "Valhalla matrix request timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_provider_error,
                "Valhalla matrix request failed.",
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_invalid_response,
                "Valhalla returned an invalid matrix response.",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    def _matrix_batches(
        self,
        locations: tuple[MatrixLocation, ...],
    ) -> tuple[
        tuple[
            int,
            tuple[MatrixLocation, ...],
            int,
            tuple[MatrixLocation, ...],
        ],
        ...,
    ]:
        return full_matrix_batches(locations, self.max_matrix_pairs)

    def _matrix_cell_cache_key(
        self,
        profile: str,
        source: MatrixLocation,
        target: MatrixLocation,
    ) -> MatrixCellCacheKey:
        return (
            self.provider_version,
            profile,
            source.canonical_key,
            target.canonical_key,
        )

    @staticmethod
    def _matrix_batch_cache_key(
        profile: str,
        sources: tuple[MatrixLocation, ...],
        targets: tuple[MatrixLocation, ...],
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        return (
            profile,
            tuple(item.canonical_key for item in sources),
            tuple(item.canonical_key for item in targets),
        )

    def _get_matrix_batch(
        self,
        key: tuple[str, tuple[str, ...], tuple[str, ...]],
    ) -> tuple[tuple[MatrixCell, ...], ...] | None:
        entry = self._matrix_batch_cache.get(key)
        if entry is None:
            return None
        expires_at, cells = entry
        if expires_at <= monotonic():
            self._matrix_batch_cache.pop(key, None)
            return None
        self._matrix_batch_cache.move_to_end(key)
        return cells

    def _put_matrix_batch(
        self,
        key: tuple[str, tuple[str, ...], tuple[str, ...]],
        cells: tuple[tuple[MatrixCell, ...], ...],
    ) -> None:
        self._matrix_batch_cache[key] = (
            monotonic() + self.matrix_batch_cache_ttl_seconds,
            cells,
        )
        self._matrix_batch_cache.move_to_end(key)
        while len(self._matrix_batch_cache) > self.matrix_batch_cache_entries:
            self._matrix_batch_cache.popitem(last=False)

    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        if not legs:
            return ()
        return await traced_call(
            "valhalla.route",
            lambda: self._route(legs, profile),
            kind="tool",
            input_summary={"legCount": len(legs), "profile": profile},
            output_summary=lambda value: {
                "routeCount": len(value),
                "provider": "valhalla",
            },
            metadata={"provider": "valhalla"},
        )

    async def _route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)

        async def fetch(leg: RouteLegRequest) -> RouteDetail:
            response = await client.post(
                f"{self.base_url}/route",
                json={
                    "locations": [
                        self._coordinate(leg.origin),
                        self._coordinate(leg.destination),
                    ],
                    "costing": self._costing(profile),
                    "units": "kilometers",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            trip = response.json()["trip"]
            summary = trip["summary"]
            return RouteDetail(
                origin_node_id=leg.origin.node_id,
                destination_node_id=leg.destination.node_id,
                duration_seconds=float(summary["time"]),
                distance_meters=float(summary["length"]) * 1000,
                encoded_polyline=trip.get("legs", [{}])[0].get("shape"),
                provider="valhalla",
            )

        try:
            return tuple(await asyncio.gather(*(fetch(leg) for leg in legs)))
        except httpx.TimeoutException as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_timeout,
                "Valhalla route request timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_provider_error,
                "Valhalla route request failed.",
            ) from exc
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RoutingPhaseError(
                RoutingErrorCode.matrix_invalid_response,
                "Valhalla returned an invalid route response.",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _coordinate(location: MatrixLocation) -> dict[str, float]:
        return {"lat": location.latitude, "lon": location.longitude}

    @staticmethod
    def _costing(profile: str) -> str:
        if profile not in {"auto", "bicycle", "pedestrian"}:
            raise ValueError(f"Unsupported Valhalla profile: {profile}")
        return profile
