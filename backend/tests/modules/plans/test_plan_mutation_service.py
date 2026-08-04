import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from uuid import uuid4

from app.modules.plans.domain.entities import (
    PlaceSelectionBlueprint,
    PlaceSelectionDay,
    Plan,
    PlanDay,
    PlanItem,
    PlanTransportLeg,
    PlanTransportOption,
    TravelIntent,
    UnscheduledPlace,
)
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    ReorderItemsRequest,
    SelectTransportOptionRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import RouteCalculation
from app.shared.errors import AppError


def make_sample_plan() -> Plan:
    return Plan(
        id=str(uuid4()),
        kind=PlanKind.main,
        status=PlanStatus.locked,
        title="Chuyến đi Hà Nội 2 ngày",
        destination="Hà Nội",
        intent=TravelIntent(
            destination="Hà Nội",
            days=2,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        macroPlan=PlaceSelectionBlueprint(
            title="Chuyến đi Hà Nội 2 ngày",
            destination="Hà Nội",
            selectionDays=[
                PlaceSelectionDay(day=1, theme="Khám phá Phố Cổ", targetArea="Hoàn Kiếm"),
                PlaceSelectionDay(day=2, theme="Văn hóa Tây Hồ", targetArea="Tây Hồ"),
            ],
        ),
        days=[
            PlanDay(
                day=1,
                theme="Khám phá Phố Cổ",
                items=[
                    PlanItem(
                        itemId="item-1-1",
                        name="Hồ Hoàn Kiếm",
                        timeWindow="09:00-10:30",
                        placeType="attraction",
                        timelineCategory="activity",
                        source="finder",
                        latitude=21.0285,
                        longitude=105.8542,
                    ),
                    PlanItem(
                        itemId="item-1-2",
                        name="Chợ Đồng Xuân",
                        timeWindow="11:00-12:30",
                        placeType="attraction",
                        timelineCategory="activity",
                        source="finder",
                        latitude=21.0375,
                        longitude=105.8500,
                    ),
                ],
            ),
            PlanDay(
                day=2,
                theme="Văn hóa Tây Hồ",
                items=[
                    PlanItem(
                        itemId="item-2-1",
                        name="Chùa Trấn Quốc",
                        timeWindow="09:30-11:00",
                        placeType="attraction",
                        timelineCategory="activity",
                        source="finder",
                        latitude=21.0478,
                        longitude=105.8368,
                    )
                ],
            ),
        ],
    )


def test_add_item_success():
    service = PlanMutationService()
    plan = make_sample_plan()

    req = AddItemRequest(
        day=1,
        name="Phở Thìn Lò Đúc",
        placeType="food",
        durationMinutes=45,
        latitude=21.0185,
        longitude=105.8545,
        notes="Ăn trưa ngon",
    )

    result = asyncio.run(service.add_item(plan, req))
    assert result.affected_days == [1]

    day1 = result.plan.days[0]
    assert len(day1.items) == 3
    added = day1.items[-1]
    assert added.name == "Phở Thìn Lò Đúc"
    assert added.source == "manual"
    assert len(day1.transport_legs) == 2


def test_add_item_at_requested_position():
    service = PlanMutationService()
    plan = make_sample_plan()

    result = asyncio.run(
        service.add_item(
            plan,
            AddItemRequest(
                day=1,
                name="Điểm dừng xen giữa",
                position=1,
                latitude=21.03,
                longitude=105.84,
            ),
        )
    )

    assert [item.name for item in result.plan.days[0].items] == [
        "Hồ Hoàn Kiếm",
        "Điểm dừng xen giữa",
        "Chợ Đồng Xuân",
    ]


def test_add_item_removes_matching_unscheduled_place():
    service = PlanMutationService()
    plan = make_sample_plan().model_copy(
        update={
            "unscheduled_places": [
                UnscheduledPlace(
                    placeId="food-1",
                    name="Phở Thìn Lò Đúc",
                    reasonCode="no_day_capacity",
                    reason="Fixed trip duration has no remaining slot.",
                )
            ]
        }
    )

    result = asyncio.run(
        service.add_item(
            plan,
            AddItemRequest(
                day=1,
                placeId="food-1",
                name="Phở Thìn Lò Đúc",
                placeType="food",
                latitude=21.0185,
                longitude=105.8545,
            ),
        )
    )

    assert result.plan.unscheduled_places == []


def test_add_item_invalid_day():
    service = PlanMutationService()
    plan = make_sample_plan()

    req = AddItemRequest(day=3, name="Invalid Day Place")
    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.add_item(plan, req))
    assert exc_info.value.status_code == 404


def test_update_item_success():
    service = PlanMutationService()
    plan = make_sample_plan()

    req = UpdateItemRequest(
        name="Hồ Gươm (Hồ Hoàn Kiếm)",
        notes="Đi dạo quanh hồ",
    )

    result = asyncio.run(
        service.update_item(plan, day_number=1, item_id="item-1-1", request=req)
    )
    updated_item = result.plan.days[0].items[0]
    assert updated_item.name == "Hồ Gươm (Hồ Hoàn Kiếm)"
    assert updated_item.notes == "Đi dạo quanh hồ"


def test_personal_notes_are_separate_from_source_context() -> None:
    service = PlanMutationService()
    plan = make_sample_plan()
    original_notes = plan.days[0].items[0].notes

    result = asyncio.run(
        service.update_item(
            plan,
            day_number=1,
            item_id="item-1-1",
            request=UpdateItemRequest(
                personalNotes="Mang theo máy ảnh và pin dự phòng."
            ),
        )
    )

    updated_item = result.plan.days[0].items[0]
    assert updated_item.notes == original_notes
    assert updated_item.personal_notes == (
        "Mang theo máy ảnh và pin dự phòng."
    )
    assert updated_item.model_dump(by_alias=True)["personalNotes"] == (
        "Mang theo máy ảnh và pin dự phòng."
    )


def test_search_place_suggestions_uses_catalog_aliases_without_accents():
    place = SimpleNamespace(
        id="place-coffee-9",
        name="Coffee 9",
        place_type="cafe",
        address="9 Phố Cà Phê, Hà Nội",
        city="Hà Nội",
        country="Việt Nam",
        country_code="vn",
        primary_area="Hoàn Kiếm",
        latitude=Decimal("21.0285"),
        longitude=Decimal("105.8542"),
        data_confidence="high",
        source_fetched_at=None,
        metadata_json={"vietnameseNames": ["Cà phê 9"]},
    )

    class FakePlaceRepository:
        def search_active_for_autocomplete(
            self,
            query,
            region_key=None,
            *,
            limit=200,
        ):
            assert query == "ca phe"
            assert region_key == "vn,ha-noi"
            assert limit == 200
            return [place]

    service = PlanMutationService(place_repository=FakePlaceRepository())

    suggestions = asyncio.run(
        service.search_place_suggestions("ca phe", destination="Hà Nội")
    )

    assert [suggestion.place_id for suggestion in suggestions] == ["place-coffee-9"]
    assert suggestions[0].name == "Coffee 9"
    assert suggestions[0].latitude == 21.0285


def test_search_place_suggestions_ranks_popular_exact_matches_first():
    quiet_branch = SimpleNamespace(
        id="quiet-branch",
        name="Phở Thìn",
        address="Tây Mỗ, Hà Nội",
        latitude=Decimal("21.005899"),
        longitude=Decimal("105.733861"),
        review_count=92,
        rating=Decimal("3.9"),
        metadata_json={},
    )
    popular_branch = SimpleNamespace(
        id="popular-branch",
        name="Phở Thìn",
        address="13 Lò Đúc, Hà Nội",
        latitude=Decimal("21.018111"),
        longitude=Decimal("105.855301"),
        review_count=1506,
        rating=Decimal("4.2"),
        metadata_json={},
    )

    class FakePlaceRepository:
        def search_active_for_autocomplete(
            self,
            query,
            region_key=None,
            *,
            limit=200,
        ):
            return [quiet_branch, popular_branch]

    service = PlanMutationService(place_repository=FakePlaceRepository())

    suggestions = asyncio.run(
        service.search_place_suggestions("Pho Thin", destination="Ha Noi")
    )

    assert [suggestion.place_id for suggestion in suggestions] == [
        "popular-branch",
        "quiet-branch",
    ]


def test_update_item_keeps_selected_catalog_identity_and_coordinates():
    service = PlanMutationService()
    plan = make_sample_plan()
    request = UpdateItemRequest(
        placeId="place-coffee-9",
        name="Coffee 9",
        address="9 Phố Cà Phê, Hà Nội",
        latitude=21.02,
        longitude=105.85,
    )

    result = asyncio.run(
        service.update_item(plan, day_number=1, item_id="item-1-1", request=request)
    )

    updated_item = result.plan.days[0].items[0]
    assert updated_item.place_id == "place-coffee-9"
    assert updated_item.address == "9 Phố Cà Phê, Hà Nội"
    assert updated_item.latitude == 21.02
    assert updated_item.longitude == 105.85


def test_remove_item_success():
    service = PlanMutationService()
    plan = make_sample_plan()

    result = service.remove_item(plan, day_number=1, item_id="item-1-1")
    day1_items = result.plan.days[0].items
    assert len(day1_items) == 1
    assert day1_items[0].item_id == "item-1-2"


def test_remove_unscheduled_place_by_place_id():
    service = PlanMutationService()
    plan = make_sample_plan().model_copy(
        update={
            "unscheduled_places": [
                UnscheduledPlace(
                    placeId="food-1",
                    name="Phở Thìn Lò Đúc",
                    reasonCode="no_day_capacity",
                    reason="Fixed trip duration has no remaining slot.",
                ),
                UnscheduledPlace(
                    placeId="cafe-1",
                    name="Cà phê Giảng",
                    reasonCode="no_day_capacity",
                    reason="Fixed trip duration has no remaining slot.",
                ),
            ]
        }
    )

    result = service.remove_unscheduled_place(
        plan,
        place_id="food-1",
        name="Phở Thìn",
    )

    assert [item.place_id for item in result.plan.unscheduled_places] == ["cafe-1"]


def test_remove_unscheduled_place_by_normalized_name():
    service = PlanMutationService()
    plan = make_sample_plan().model_copy(
        update={
            "unscheduled_places": [
                UnscheduledPlace(
                    name="Cà phê Giảng",
                    reasonCode="no_day_capacity",
                    reason="Fixed trip duration has no remaining slot.",
                )
            ]
        }
    )

    result = service.remove_unscheduled_place(plan, name="ca phe giang")

    assert result.plan.unscheduled_places == []


def test_remove_unknown_unscheduled_place_returns_not_found():
    service = PlanMutationService()
    plan = make_sample_plan()

    with pytest.raises(AppError) as exc_info:
        service.remove_unscheduled_place(plan, name="Không tồn tại")

    assert exc_info.value.status_code == 404


def test_move_item_between_days():
    service = PlanMutationService()
    plan = make_sample_plan()

    req = MoveItemRequest(toDay=2, position=0)
    result = service.move_item(plan, from_day_number=1, item_id="item-1-2", request=req)

    assert result.affected_days == [1, 2]
    assert len(result.plan.days[0].items) == 1
    assert len(result.plan.days[1].items) == 2
    assert result.plan.days[1].items[0].item_id == "item-1-2"


def test_reorder_items_success():
    service = PlanMutationService()
    plan = make_sample_plan()

    req = ReorderItemsRequest(itemIds=["item-1-2", "item-1-1"])
    result = service.reorder_items(plan, day_number=1, request=req)

    items = result.plan.days[0].items
    assert items[0].item_id == "item-1-2"
    assert items[1].item_id == "item-1-1"


def test_reorder_items_saves_new_order_and_recalculates_valhalla_legs():
    route_provider = RecordingValhallaRouteProvider()
    service = PlanMutationService(
        route_optimizer=GeographicRouteOptimizer(route_provider)
    )
    plan = make_sample_plan()

    result = service.reorder_items(
        plan,
        day_number=1,
        request=ReorderItemsRequest(itemIds=["item-1-2", "item-1-1"]),
    )

    day = result.plan.days[0]
    assert [item.item_id for item in day.items] == ["item-1-2", "item-1-1"]
    assert day.items[0].time_window.startswith("09:00-")
    assert len(day.transport_legs) == 1
    assert day.transport_legs[0].from_item_id == "item-1-2"
    assert day.transport_legs[0].to_item_id == "item-1-1"
    assert day.transport_legs[0].source == "valhalla_routing"
    assert day.transport_legs[0].verified is True
    assert route_provider.requested_pairs == [
        ((21.0375, 105.85), (21.0285, 105.8542), "pedestrian"),
        ((21.0375, 105.85), (21.0285, 105.8542), "car"),
    ]


def test_reorder_items_reuses_route_legs_that_remain_adjacent():
    route_provider = RecordingValhallaRouteProvider()
    service = PlanMutationService(
        route_optimizer=GeographicRouteOptimizer(route_provider)
    )
    plan = make_sample_plan()
    original_items = [
        plan.days[0].items[0].model_copy(
            update={"duration_minutes": 60, "time_window": "09:00-10:00"}
        ),
        plan.days[0].items[1].model_copy(
            update={"duration_minutes": 60, "time_window": "10:15-11:15"}
        ),
    ]
    extra_items = [
        PlanItem(
            itemId="item-1-3",
            name="Nhà hát Lớn Hà Nội",
            timeWindow="11:30-12:30",
            placeType="attraction",
            timelineCategory="activity",
            source="finder",
            durationMinutes=60,
            latitude=21.0243,
            longitude=105.8575,
        ),
        PlanItem(
            itemId="item-1-4",
            name="Bảo tàng Lịch sử Quốc gia",
            timeWindow="12:45-13:45",
            placeType="attraction",
            timelineCategory="activity",
            source="finder",
            durationMinutes=60,
            latitude=21.0245,
            longitude=105.8584,
        ),
    ]
    items = [*original_items, *extra_items]
    existing_legs = [
        PlanTransportLeg(
            fromItemId=origin.item_id,
            toItemId=destination.item_id,
            fromPlace=origin.name,
            toPlace=destination.name,
            mode="walk",
            distanceMeters=250,
            estimatedDurationMinutes=4,
            geometryCoordinates=[
                (origin.latitude, origin.longitude),
                (destination.latitude, destination.longitude),
            ],
            source="valhalla_routing",
            verified=True,
        )
        for origin, destination in zip(items, items[1:])
    ]
    plan = plan.model_copy(
        update={
            "days": [
                plan.days[0].model_copy(
                    update={"items": items, "transport_legs": existing_legs}
                ),
                plan.days[1],
            ]
        }
    )

    result = service.reorder_items(
        plan,
        day_number=1,
        request=ReorderItemsRequest(
            itemIds=["item-1-2", "item-1-1", "item-1-3", "item-1-4"]
        ),
    )

    day = result.plan.days[0]
    assert [(leg.from_item_id, leg.to_item_id) for leg in day.transport_legs] == [
        ("item-1-2", "item-1-1"),
        ("item-1-1", "item-1-3"),
        ("item-1-3", "item-1-4"),
    ]
    assert len(route_provider.requested_pairs) == 4
    assert day.transport_legs[-1] == existing_legs[-1]


def test_select_transport_option_promotes_choice_without_reordering_items():
    service = PlanMutationService()
    plan = make_sample_plan()
    day = plan.days[0].model_copy(
        update={
            "transport_legs": [
                PlanTransportLeg(
                    fromItemId="item-1-1",
                    toItemId="item-1-2",
                    fromPlace="Hồ Hoàn Kiếm",
                    toPlace="Chợ Đồng Xuân",
                    mode="car",
                    distanceMeters=2200,
                    estimatedDurationMinutes=12,
                    geometryCoordinates=[
                        (21.0285, 105.8542),
                        (21.0375, 105.8500),
                    ],
                    source="valhalla_routing",
                    verified=True,
                    alternatives=[
                        PlanTransportOption(
                            mode="walk",
                            distanceMeters=1600,
                            estimatedDurationMinutes=24,
                            geometryCoordinates=[
                                (21.0285, 105.8542),
                                (21.0375, 105.8500),
                            ],
                            source="valhalla_routing",
                            verified=True,
                        )
                    ],
                )
            ]
        }
    )
    plan = plan.model_copy(update={"days": [day, plan.days[1]]})

    result = service.select_transport_option(
        plan,
        day_number=1,
        leg_index=0,
        request=SelectTransportOptionRequest(mode="walk"),
    )

    updated_day = result.plan.days[0]
    assert [item.item_id for item in updated_day.items] == ["item-1-1", "item-1-2"]
    assert updated_day.transport_legs[0].mode == "walk"
    assert updated_day.transport_legs[0].estimated_duration_minutes == 24
    assert [option.mode for option in updated_day.transport_legs[0].alternatives] == [
        "car"
    ]


def test_select_transport_option_uses_option_key_for_repeated_mode_variants():
    service = PlanMutationService()
    plan = make_sample_plan()
    day = plan.days[0].model_copy(
        update={
            "transport_legs": [
                PlanTransportLeg(
                    fromItemId="item-1-1",
                    toItemId="item-1-2",
                    fromPlace="Hồ Hoàn Kiếm",
                    toPlace="Chợ Đồng Xuân",
                    mode="public_transit",
                    distanceMeters=2900,
                    estimatedDurationMinutes=32,
                    geometryCoordinates=[
                        (21.0285, 105.8542),
                        (21.0375, 105.8500),
                    ],
                    source="opentripplanner_transit",
                    verified=True,
                    details={
                        "lines": ["14"],
                        "segments": [
                            {
                                "mode": "BUS",
                                "line": "14",
                                "estimatedDurationMinutes": 20,
                                "distanceMeters": 2200,
                            }
                        ],
                    },
                    alternatives=[
                        PlanTransportOption(
                            mode="public_transit",
                            distanceMeters=2900,
                            estimatedDurationMinutes=32,
                            geometryCoordinates=[
                                (21.0285, 105.8542),
                                (21.0320, 105.8520),
                                (21.0375, 105.8500),
                            ],
                            source="opentripplanner_transit",
                            verified=True,
                            details={
                                "lines": ["31"],
                                "segments": [
                                    {
                                        "mode": "BUS",
                                        "line": "31",
                                        "estimatedDurationMinutes": 18,
                                        "distanceMeters": 2100,
                                    }
                                ],
                            },
                        )
                    ],
                )
            ]
        }
    )
    plan = plan.model_copy(update={"days": [day, plan.days[1]]})

    result = service.select_transport_option(
        plan,
        day_number=1,
        leg_index=0,
        request=SelectTransportOptionRequest(
            mode="public_transit",
            optionKey="public_transit::opentripplanner_transit::32::2900::31::BUS:31:18:2100",
            source="opentripplanner_transit",
            distanceMeters=2900,
            estimatedDurationMinutes=32,
        ),
    )

    leg = result.plan.days[0].transport_legs[0]
    assert leg.details["lines"] == ["31"]
    assert len(leg.geometry_coordinates) == 3
    assert [option.details["lines"] for option in leg.alternatives] == [["14"]]


def test_select_transport_option_rejects_unavailable_mode():
    service = PlanMutationService()
    plan = make_sample_plan()
    day = plan.days[0].model_copy(
        update={
            "transport_legs": [
                PlanTransportLeg(
                    fromPlace="Hồ Hoàn Kiếm",
                    toPlace="Chợ Đồng Xuân",
                    mode="car",
                    distanceMeters=2200,
                    estimatedDurationMinutes=12,
                    source="valhalla_routing",
                    verified=True,
                )
            ]
        }
    )
    plan = plan.model_copy(update={"days": [day, plan.days[1]]})

    with pytest.raises(AppError) as exc_info:
        service.select_transport_option(
            plan,
            day_number=1,
            leg_index=0,
            request=SelectTransportOptionRequest(mode="bus"),
        )

    assert exc_info.value.status_code == 400


class RecordingValhallaRouteProvider:
    def __init__(self) -> None:
        self.requested_pairs: list[
            tuple[tuple[float, float], tuple[float, float], str]
        ] = []

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        transport_mode: str,
        departure_time: datetime | None = None,
    ) -> RouteCalculation:
        del departure_time
        self.requested_pairs.append((origin, destination, transport_mode))
        return RouteCalculation(
            distance_meters=900 if transport_mode == "pedestrian" else 1400,
            duration_seconds=600 if transport_mode == "pedestrian" else 240,
            geometry_coordinates=[origin, destination],
            provider="valhalla_routing",
            fetched_at=datetime.now(timezone.utc),
        )
