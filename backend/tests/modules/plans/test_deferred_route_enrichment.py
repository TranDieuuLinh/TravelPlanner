from datetime import datetime, timezone

from app.modules.plans.domain.entities import Plan, PlanDay, PlanItem, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import RouteCalculation


class BatchRouteProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def calculate_many(
        self,
        coordinates,
        *,
        transport_mode,
        departure_time=None,
    ):
        del departure_time
        self.calls.append(transport_mode)
        return [
            RouteCalculation(
                distance_meters=900,
                duration_seconds=600,
                geometry_coordinates=[origin, destination],
                provider="valhalla_routing",
                fetched_at=datetime.now(timezone.utc),
            )
            for origin, destination in zip(coordinates, coordinates[1:])
        ]


class UnavailableBatchRouteProvider:
    def calculate_many(
        self,
        coordinates,
        *,
        transport_mode,
        departure_time=None,
    ):
        del coordinates, transport_mode, departure_time
        return None


def test_deferred_enrichment_replaces_coarse_leg_in_separate_step() -> None:
    provider = BatchRouteProvider()
    selector = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(
            GeographicRouteOptimizer(provider)
        )
    )
    first = PlanItem(
        itemId="a",
        name="A",
        timeWindow="09:00-10:00",
        placeType="attraction",
        latitude=21.028,
        longitude=105.852,
    )
    second = PlanItem(
        itemId="b",
        name="B",
        timeWindow="10:30-11:30",
        placeType="attraction",
        latitude=21.030,
        longitude=105.858,
    )
    _, coarse_legs = GeographicRouteOptimizer().optimize(
        [first, second],
        preserve_order=True,
    )
    plan = Plan(
        id="plan-deferred-route",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Deferred route",
        destination="Hà Nội",
        intent=TravelIntent(
            destination="Hà Nội",
            days=1,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        days=[
            PlanDay(
                day=1,
                theme="Test",
                items=[first, second],
                transportLegs=coarse_legs,
            )
        ],
        routeEnrichmentStatus="pending",
    )

    assert provider.calls == []
    assert plan.days[0].transport_legs[0].verified is False

    enriched = selector.enrich_plan_routes(plan)

    assert provider.calls == ["pedestrian"]
    assert enriched.route_enrichment_status == "completed"
    assert enriched.days[0].transport_legs[0].verified is True
    assert enriched.days[0].transport_legs[0].source == "valhalla_routing"


def test_deferred_enrichment_is_failed_when_only_coarse_fallback_remains() -> None:
    selector = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(
            GeographicRouteOptimizer(UnavailableBatchRouteProvider())
        )
    )
    first = PlanItem(
        itemId="a",
        name="A",
        timeWindow="09:00-10:00",
        placeType="attraction",
        latitude=21.028,
        longitude=105.852,
    )
    second = PlanItem(
        itemId="b",
        name="B",
        timeWindow="10:30-11:30",
        placeType="attraction",
        latitude=21.030,
        longitude=105.858,
    )
    plan = Plan(
        id="plan-failed-route",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Unavailable route",
        destination="Hà Nội",
        intent=TravelIntent(
            destination="Hà Nội",
            days=1,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        days=[
            PlanDay(
                day=1,
                theme="Test",
                items=[first, second],
            )
        ],
        routeEnrichmentStatus="pending",
    )

    enriched = selector.enrich_plan_routes(plan)

    assert enriched.route_enrichment_status == "failed"
    assert enriched.days[0].transport_legs[0].source == "geodesic_estimate"
