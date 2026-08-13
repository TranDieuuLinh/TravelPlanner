from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    RoutingErrorCode,
    RoutingPhaseError,
    TravelMatrix,
)


class ValhallaAdapter:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15,
        provider_version: str = "unknown",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.provider_version = provider_version

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/sources_to_targets",
                json={
                    "sources": [self._coordinate(item) for item in locations],
                    "targets": [self._coordinate(item) for item in locations],
                    "costing": self._costing(profile),
                    "units": "kilometers",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return self._parse_matrix(response.json(), locations, profile)
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

    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        if not legs:
            return ()
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

    def _parse_matrix(
        self,
        payload: dict[str, Any],
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        rows = payload["sources_to_targets"]
        if len(rows) != len(locations):
            raise ValueError("matrix row count mismatch")
        parsed_rows: list[tuple[MatrixCell, ...]] = []
        for row in rows:
            if len(row) != len(locations):
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
        return TravelMatrix(
            node_ids=tuple(item.node_id for item in locations),
            cells=tuple(parsed_rows),
            profile=profile,
            provider="valhalla",
            provider_version=self.provider_version,
        )

    @staticmethod
    def _coordinate(location: MatrixLocation) -> dict[str, float]:
        return {"lat": location.latitude, "lon": location.longitude}

    @staticmethod
    def _costing(profile: str) -> str:
        if profile not in {"auto", "bicycle", "pedestrian"}:
            raise ValueError(f"Unsupported Valhalla profile: {profile}")
        return profile
