from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
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
    macro = MacroPlan(
        title="Hải Phòng",
        destination="Hải Phòng",
        regionKey="vn,hai-phong",
        dayBriefs=[
            DayBrief(
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
