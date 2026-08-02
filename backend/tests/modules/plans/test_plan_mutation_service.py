import asyncio

import pytest
from uuid import uuid4

from app.modules.plans.domain.entities import (
    MacroPlan,
    DayBrief,
    Plan,
    PlanDay,
    PlanItem,
    TravelIntent,
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
        service.update_item(
            plan,
            day_number=1,
            item_id="item-1-1",
            request=req,
        )
    )
    updated_item = result.plan.days[0].items[0]
    assert updated_item.name == "Hồ Gươm (Hồ Hoàn Kiếm)"
    assert updated_item.notes == "Đi dạo quanh hồ"


def test_remove_item_success():
    service = PlanMutationService()
    plan = make_sample_plan()

    result = service.remove_item(plan, day_number=1, item_id="item-1-1")
    day1_items = result.plan.days[0].items
    assert len(day1_items) == 1
    assert day1_items[0].item_id == "item-1-2"


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
