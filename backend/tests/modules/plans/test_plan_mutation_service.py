import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from uuid import uuid4

from app.modules.plans.domain.entities import (
    MacroPlan,
    DayBrief,
    Plan,
    PlanDay,
    PlanItem,
    TravelIntent,
    UnscheduledPlace,
)
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    ReorderItemsRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
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
        macroPlan=MacroPlan(
            title="Chuyến đi Hà Nội 2 ngày",
            destination="Hà Nội",
            dayBriefs=[
                DayBrief(day=1, theme="Khám phá Phố Cổ", targetArea="Hoàn Kiếm"),
                DayBrief(day=2, theme="Văn hóa Tây Hồ", targetArea="Tây Hồ"),
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
        def list_active_for_planner_research(self, region_key=None, *, limit=5000):
            assert region_key == "vn,ha-noi"
            return [place]

    service = PlanMutationService(place_repository=FakePlaceRepository())

    suggestions = asyncio.run(
        service.search_place_suggestions("ca phe", destination="Hà Nội")
    )

    assert [suggestion.place_id for suggestion in suggestions] == ["place-coffee-9"]
    assert suggestions[0].name == "Coffee 9"
    assert suggestions[0].latitude == 21.0285


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
