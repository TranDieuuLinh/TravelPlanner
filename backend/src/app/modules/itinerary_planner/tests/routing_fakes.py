from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    TravelMatrix,
)


class GeneratedMatrixProvider:
    def __init__(self, *, asymmetric: bool = False) -> None:
        self.calls = 0
        self.asymmetric = asymmetric

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        self.calls += 1
        rows = []
        for origin in range(len(locations)):
            row = []
            for destination in range(len(locations)):
                if origin == destination:
                    seconds = distance = 0
                else:
                    direction = origin * 120 if self.asymmetric else 0
                    seconds = 300 + abs(origin - destination) * 60 + direction
                    distance = 1000 + abs(origin - destination) * 100
                row.append(MatrixCell(seconds, distance, True))
            rows.append(tuple(row))
        return TravelMatrix(
            node_ids=tuple(item.node_id for item in locations),
            cells=tuple(rows),
            profile=profile,
            provider="fake",
            provider_version="test-v1",
        )


class FixedCostEstimator:
    def estimate(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> tuple[int, int]:
        return distance_meters // 10, 0


class GeneratedRouteDetailProvider:
    def __init__(
        self,
        *,
        duration_seconds: float = 360,
        duration_by_pair: dict[tuple[str, str], float] | None = None,
    ) -> None:
        self.duration_seconds = duration_seconds
        self.duration_by_pair = duration_by_pair or {}
        self.calls: list[tuple[RouteLegRequest, ...]] = []

    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        self.calls.append(legs)
        return tuple(
            RouteDetail(
                origin_node_id=leg.origin.node_id,
                destination_node_id=leg.destination.node_id,
                duration_seconds=self.duration_by_pair.get(
                    (leg.origin.node_id, leg.destination.node_id),
                    self.duration_seconds,
                ),
                distance_meters=1200,
                encoded_polyline="encoded-test-shape",
                provider="fake-route",
            )
            for leg in legs
        )
