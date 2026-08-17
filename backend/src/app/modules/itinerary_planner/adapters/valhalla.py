from __future__ import annotations

import asyncio
from math import ceil
from typing import Any

import httpx

from app.shared.observability import traced_call

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


class ValhallaAdapter:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
        provider_version: str = "unknown",
        max_matrix_pairs: int = DEFAULT_MAX_MATRIX_PAIRS,
        matrix_concurrency: int = DEFAULT_MATRIX_CONCURRENCY,
    ) -> None:
        if max_matrix_pairs < 1:
            raise ValueError("max_matrix_pairs must be positive")
        if matrix_concurrency < 1:
            raise ValueError("matrix_concurrency must be positive")
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.provider_version = provider_version
        self.max_matrix_pairs = max_matrix_pairs
        self.matrix_concurrency = matrix_concurrency

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
            source_start: int,
            sources: tuple[MatrixLocation, ...],
            target_start: int,
            targets: tuple[MatrixLocation, ...],
        ) -> tuple[int, int, tuple[tuple[MatrixCell, ...], ...]]:
            async with semaphore:
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
            return (
                source_start,
                target_start,
                self._parse_matrix_cells(response.json(), len(sources), len(targets)),
            )

        try:
            batches = self._matrix_batches(locations)
            results = await asyncio.gather(
                *(
                    fetch(source_start, sources, target_start, targets)
                    for source_start, sources, target_start, targets in batches
                )
            )
            rows: list[list[MatrixCell | None]] = [
                [None] * len(locations) for _ in locations
            ]
            for source_start, target_start, cells in results:
                for source_offset, row in enumerate(cells):
                    for target_offset, cell in enumerate(row):
                        rows[source_start + source_offset][
                            target_start + target_offset
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
        size = len(locations)
        if size == 0:
            return ()
        source_chunk, target_chunk = _matrix_batch_shape(
            size, self.max_matrix_pairs
        )
        return tuple(
            (
                source_start,
                locations[source_start : source_start + source_chunk],
                target_start,
                locations[target_start : target_start + target_chunk],
            )
            for source_start in range(0, size, source_chunk)
            for target_start in range(0, size, target_chunk)
        )

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
    def _parse_matrix_cells(
        payload: dict[str, Any],
        source_count: int,
        target_count: int,
    ) -> tuple[tuple[MatrixCell, ...], ...]:
        rows = payload["sources_to_targets"]
        if len(rows) != source_count:
            raise ValueError("matrix row count mismatch")
        parsed_rows: list[tuple[MatrixCell, ...]] = []
        for row in rows:
            if len(row) != target_count:
                raise ValueError("matrix column count mismatch")
            parsed: list[MatrixCell] = []
            for cell in row:
                duration = cell.get("time")
                distance = cell.get("distance")
                reachable = duration is not None and distance is not None
                if reachable and (float(duration) < 0 or float(distance) < 0):
                    raise ValueError("negative matrix value")
                parsed.append(
                    MatrixCell(
                        duration_seconds=float(duration) if reachable else None,
                        distance_meters=float(distance) * 1000 if reachable else None,
                        reachable=reachable,
                    )
                )
            parsed_rows.append(tuple(parsed))
        return tuple(parsed_rows)

    @staticmethod
    def _coordinate(location: MatrixLocation) -> dict[str, float]:
        return {"lat": location.latitude, "lon": location.longitude}

    @staticmethod
    def _costing(profile: str) -> str:
        if profile not in {"auto", "bicycle", "pedestrian"}:
            raise ValueError(f"Unsupported Valhalla profile: {profile}")
        return profile


def _matrix_batch_shape(size: int, max_pairs: int) -> tuple[int, int]:
    """Choose chunks that minimize request count without exceeding max_pairs."""
    best: tuple[int, int, int, int] | None = None
    for target_chunk in range(1, min(size, max_pairs) + 1):
        source_chunk = min(size, max_pairs // target_chunk)
        request_count = ceil(size / source_chunk) * ceil(size / target_chunk)
        covered_pairs = source_chunk * target_chunk
        candidate = (request_count, -covered_pairs, -target_chunk, source_chunk)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return best[3], -best[2]
