from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import (
    PlaceSelectionDay,
    PlaceSelectionBlueprint,
    Plan,
    PlanDay,
    PlanItem,
    TravelIntent,
)
from app.modules.plans.domain.enums import (
    BudgetLevel,
    PlanKind,
    PlanStatus,
    TravelPace,
)


def test_overall_checker_fails_plan_that_violates_constraint_policy() -> None:
    intent = TravelIntent(
        destination="Hải Phòng",
        days=1,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        constraintPolicy={
            "excludedPlaceTypes": ["cemetery"],
            "geographicScope": {"type": "coastal"},
        },
    )
    macro = PlaceSelectionBlueprint(
        title="Hải Phòng",
        destination="Hải Phòng",
        regionKey="vn,hai-phong",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Ven biển",
                targetArea="Đồ Sơn",
                targetRegionKey="vn,hai-phong,do-son",
            )
        ],
    )
    plan = Plan(
        id="plan-constraint",
        kind=PlanKind.main,
        status=PlanStatus.checking,
        title="Hải Phòng",
        destination="Hải Phòng",
        intent=intent,
        macroPlan=macro,
        days=[
            PlanDay(
                day=1,
                theme="Ven biển",
                items=[
                    PlanItem(
                        itemId="cemetery-item",
                        name="Nghĩa trang liệt sĩ",
                        timeWindow="09:00-10:00",
                        placeType="cemetery",
                        regionKey="vn,hai-phong,do-son",
                        source="finder_suggestion",
                        tags=["coastal"],
                    )
                ],
            )
        ],
    )

    report = OverallChecker().check(plan)

    assert report.status == "failed"
    assert any(
        issue.code == "excluded_place_type"
        and issue.affected_item_ids == ["cemetery-item"]
        for issue in report.issues
    )


def test_overall_checker_rejects_time_windows_beyond_local_day() -> None:
    plan = _plan_with_items(
        [
            PlanItem(
                itemId="overflow",
                name="Late stop",
                timeWindow="24:07-25:07",
                placeType="attraction",
            )
        ]
    )

    report = OverallChecker().check(plan)

    assert report.status == "failed"
    assert any(
        issue.code == "invalid_time_window"
        and issue.affected_item_ids == ["overflow"]
        for issue in report.issues
    )


def test_overall_checker_rejects_day_above_pace_capacity() -> None:
    plan = _plan_with_items(
        [
            PlanItem(
                itemId=f"activity-{index}",
                name=f"Activity {index}",
                timeWindow=f"{8 + index:02d}:00-{9 + index:02d}:00",
                placeType="attraction",
            )
            for index in range(4)
        ]
    )

    report = OverallChecker().check(plan)

    assert report.status == "failed"
    assert any(
        issue.code == "day_activity_capacity_exceeded"
        and issue.affected_item_ids == ["activity-3"]
        for issue in report.issues
    )


def _plan_with_items(items: list[PlanItem]) -> Plan:
    intent = TravelIntent(
        destination="Hà Nội",
        days=1,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
    )
    macro = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Khám phá",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
            )
        ],
    )
    return Plan(
        id="plan-check",
        kind=PlanKind.main,
        status=PlanStatus.checking,
        title="Hà Nội",
        destination="Hà Nội",
        intent=intent,
        macroPlan=macro,
        days=[PlanDay(day=1, theme="Khám phá", items=items)],
    )
